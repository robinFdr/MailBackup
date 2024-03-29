
import base64
import email
import imaplib
import json
import os
import sys
import threading
import tkinter
import traceback
from datetime import datetime, timedelta
from email.message import Message
from tkinter import Button, Label, StringVar, Tk, ttk
from tkinter.simpledialog import askstring

import jinja2


class ProgressWindow:
    def __init__(self, title: str) -> None:
        self.window = Tk()
        self.window.title(title)
        self.window.iconbitmap(default='./config/MailBackup.ico')
        self.window.attributes('-topmost', True)
        self.progressBar = ttk.Progressbar(
            master=self.window, orient=tkinter.HORIZONTAL, length=300)
        self.progressBar.pack(padx=10, pady=5)
        self.messageVar = StringVar(self.window)
        self.messageLabel = Label(self.window, textvariable=self.messageVar)
        self.messageLabel.pack()
        self.button = None

    def addButtonWithFunction(self, buttonText: str, buttonFunction, parameters: tuple):
        self.buttonFunction = buttonFunction
        self.buttonFunctionParameters = parameters
        self.button = Button(master=self.window,
                             text=buttonText, command=lambda: self.__buttonClicked())
        self.button.pack(pady=5)

    def __buttonClicked(self):
        if (self.button != None):
            self.button['state'] = tkinter.DISABLED
        threading.Thread(target=self.buttonFunction(
            self.buttonFunctionParameters)).start()

    def updateBar(self, message: str, percent: int):
        self.progressBar['value'] = percent
        self.messageVar.set(message)
        self.window.update()
        self.window.update_idletasks()

    def runGUI(self):
        self.window.update()
        height = self.window.winfo_height()
        width = self.window.winfo_width()
        screenHeight = self.window.winfo_screenheight()
        screenWidth = self.window.winfo_screenwidth()
        self.window.geometry('{width}x{height}+{screenPosX}+{screenPosY}'.format(width=width, height=height,
                             screenPosX=int(screenWidth-(width+8)), screenPosY=int(screenHeight-(height+79))))
        self.window.mainloop()


class SaveMails:
    def __init__(self) -> None:
        self.resources:dict = json.load(open('./config/resources.json'))
        self.savedMails = []

    def createStorage(self) -> None:
        now = datetime.now().strftime('%Y%m%d-%H%M')
        self.backupFolder = os.path.join(
            self.resources['storageLocation'], self.currentAccount['username'], 'backup_' + now)
        if not os.path.exists(self.backupFolder):
            os.makedirs(self.backupFolder)
        self.folderLocations = []
        for folder in self.folders:
            cleanFoldername = SaveMails.clean(folder, '/\\').replace(
                '/', os.path.sep).replace('\\', os.path.sep)
            folderLocation = self.backupFolder + os.path.sep + cleanFoldername
            if not os.path.exists(folderLocation):
                os.makedirs(folderLocation)
            self.folderLocations.append(folderLocation)

    def backupMails(self, progress: ProgressWindow):
        for i, account in enumerate(self.resources['accounts']):
            self.currentAccount = account
            progress.window.title('Mail Backup - ' + account['username'])
            progress.updateBar('Performing Login', 0)
            self.login()
            progress.updateBar('Performing Login', 100)
            self.createStorage()
            progress.updateBar('Folder Structure created', 20)
            self.resources['accounts'][i]['password_enc'] = self.currentAccount['password_enc']
            for idx, folder in enumerate(self.folders):
                self.backupMailsInFolder(idx, folder, progress)
            self.resources['lastBackupDate'] = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            self.saveResources()
            progress.updateBar('Creating Overview Html File', 50)
            self.createHtml()
            self.imap.logout()

    def backupMailsInFolder(self, idx: int, folder: str, progress: ProgressWindow):
        status, countMessagesBytesList = self.imap.select(folder)
        if status != 'OK':
            print("Error accessing folder: " + folder)
            return
        if 'lastBackupDate' in self.resources.keys():
            datestr = self.resources['lastBackupDate']
            datestr = datetime.strptime(datestr, '%Y-%m-%d').strftime('%d-%b-%Y')
            typ, [msgnums] = self.imap.search(None, f'(since "{datestr}")')
            if len(msgnums.decode('utf-8')) < 1:
                return
            for no, i in enumerate(msgnums.decode('utf-8').split(' ')):
                # to add a filter for downloading only latest emails (after e.g. last backup date): https://gist.github.com/zed/9336086
                # another interesting library: https://pypi.org/project/imap-tools/#actions-with-emails msg.obj == raw_mail
                try:
                    res, raw_mail = self.imap.fetch(str(i), '(RFC822)')
                    progressMessage = '({0}/{1}) Folder: {2} ({3}/{4}) - {5}'.format(
                        idx, len(self.folders), folder, no, len(msgnums), str(res)
                    )
                    progressPercentage = int((float(i)/float(len(msgnums)))*100)
                    progress.updateBar(progressMessage, progressPercentage)
                    self.saveMail(
                        raw_mail[0][1], self.folderLocations[idx], folderName=folder)
                except Exception as e:
                    try:
                        print('Failed to save mail: ' + str(i) + ' ' + self.subjectOf(email.message_from_bytes(raw_mail)) +
                            ' in folder ' + str(idx) + ' ' + folder + ' for folderLocation: ' + self.folderLocations[idx])
                    except:
                        pass
                    traceback.print_exception(e)
        else:
            n = int(countMessagesBytesList[0])
            for i in range(1, n+1):
                # to add a filter for downloading only latest emails (after e.g. last backup date): https://gist.github.com/zed/9336086
                # another interesting library: https://pypi.org/project/imap-tools/#actions-with-emails msg.obj == raw_mail
                try:
                    res, raw_mail = self.imap.fetch(str(i), '(RFC822)')
                    progressMessage = '({0}/{1}) Folder: {2} ({3}/{4}) - {5}'.format(
                        idx, len(self.folders), folder, i, n, str(res))
                    progressPercentage = int((float(i)/float(n))*100)
                    progress.updateBar(progressMessage, progressPercentage)
                    try:
                        rawBytes = raw_mail[0][1]
                    except:
                        print("Couldn't access raw bytes")
                    folderLocation = self.folderLocations[idx]
                    self.saveMail(
                        rawBytes, folderLocation, folderName=folder)
                except Exception as e:
                    try:
                        print('Failed to save mail: ' + str(i) + ' ' + self.subjectOf(email.message_from_bytes(raw_mail)) +
                            ' in folder ' + str(idx) + ' ' + folder + ' for folderLocation: ' + self.folderLocations[idx])
                    except:
                        pass
                    traceback.print_exception(e)

    def saveMail(self, rawMail: bytes, folderLocation, folderName):
        try:
            mail = email.message_from_bytes(rawMail)
            path = self.filepathOf(mail, folderLocation)
            with open(path, 'wb') as mailFile:
                mailFile.write(rawMail)
            date = self.dateOf(mail)
            if (date == None):
                date = 'Not available'
            else:
                date = date.strftime('%d.%m.%Y %H:%M Uhr')
            self.savedMails.append({
                "folder": folderName,
                "fileLocation": '.' + path[len(self.backupFolder):],
                "subject": self.subjectOf(mail),
                "from": self.decodeHeader(header='from', mail=mail),
                "to": self.decodeHeader('to', mail),
                "date": date,
                "attachments": self.countAttachments(mail)
            })
            return True
        except Exception as e:
            traceback.print_exception(e)
            return False

    def filepathOf(self, mail: Message, folderLocation: str):
        prefix = ''
        date = self.dateOf(mail)
        if date == None:
            prefix = '00000000-0000_'
        else:
            prefix = date.strftime('%Y%m%d-%H%M_')
        subject = SaveMails.clean(self.subjectOf(mail))
        path = os.path.join(folderLocation, prefix + subject + '.eml')
        while (os.path.exists(path)):
            path = path[:-4] + '(1).eml'
        return path

    def dateOf(self, mail: Message) -> (datetime | None):
        dateStr = mail.get('date')
        if dateStr == None:
            return None
        try:
            date: datetime = email.utils.parsedate_to_datetime(dateStr)
            return date
        except Exception as e:
            return None

    def subjectOf(self, mail: Message):
        return self.decodeHeader('subject', mail)

    def decodeHeader(self, header: str, mail: Message):
        header = mail.get(header)
        if header == None:
            return ''
        if type(header) == str and not '=?' in header:
            return header
        try:
            decoded_pairs = email.header.decode_header(header)
            header = ''
            for pair in decoded_pairs:
                headerBytes:(bytes|str) = pair[0]
                charset: str = pair[1]
                if charset == None:
                    charset = 'utf-8'
                try:
                    header += headerBytes.decode(charset)
                except:
                    try:
                        if type(headerBytes) == bytes:
                            header += headerBytes.decode('utf-8')
                        else:
                            header += str(headerBytes)
                    except Exception as exp:
                        print(
                            'Failed to extract Header. Uknown encoding: ' + charset)
                        raise (exp)
        except Exception as e:
            print("Using as header: " + str(header))
        return str(header)

    def clean(text, allowAdditionalCharacters=''):
        # clean text for creating a folder
        if ' ' in text and (text[0] == text[-1] == '"' or text[0] == text[-1] == "'"):
            text = text[1:-1]
        return "".join(c if c.isalnum() or c in '().-, =!' or c in allowAdditionalCharacters else "" for c in text)

    def encode(s: str):
        return base64.b64encode(s.encode(encoding='utf-8')).decode(encoding='utf-8')

    def decode(self, s: str):
        return base64.b64decode(s).decode(encoding='utf-8')

    def createHtml(self):
        templateLoader = jinja2.FileSystemLoader(searchpath="./config")
        templateEnv = jinja2.Environment(loader=templateLoader)
        TEMPLATE_FILE = "template.html"
        template = templateEnv.get_template(TEMPLATE_FILE)
        template.stream(account=self.currentAccount['username'], now=datetime.now().strftime(
            '%d.%m.%Y'), mails=self.savedMails).dump(os.path.join(self.backupFolder, 'index.html'))

    def login(self):
        repeat = True
        while (repeat):
            if not 'password_enc' in self.currentAccount.keys() or self.currentAccount['password_enc'] == None or self.currentAccount['password_enc'] == '':
                password = None
                while (password == None):
                    password = askstring('Mail Password', prompt='Enter Password for ' +
                                         self.currentAccount['username'] + ':' + (' '*30), show='*')
                self.currentAccount['password_enc'] = SaveMails.encode(
                    password)
            else:
                password = self.decode(self.currentAccount['password_enc'])

            try:
                self.imap = imaplib.IMAP4_SSL(
                    self.currentAccount['server'], port=int(self.currentAccount['port']))
                status, somebytes = self.imap.login(
                    self.currentAccount['username'], password)
                if (status != 'OK'):
                    raise Exception(status, 'Login Failed')
                repeat = False
                self.folders = [x.decode().split('"/" ')[1]
                                for x in self.imap.list()[1]]
            except Exception as e:
                traceback.print_exception(e)

    def saveResources(self):
        with open('./config/resources.json', 'w') as resourceFile:
            resourceFile.write(json.dumps(
                self.resources, sort_keys=True, indent=4))

    def countAttachments(self, msg: Message):
        # from https://cds.lol/tutorial/3984392-in-python,-how-can-i-count-the-number-of-files-a-sender-has-attached-to-an-email?
        totalattachments = 0
        firsttextattachmentseen = False
        lastseenboundary = ''
        alternativetextplainfound = False
        alternativetexthtmlfound = False
        for part in msg.walk():
            if part.is_multipart():
                lastseenboundary = part.get_content_type()
                continue
            if lastseenboundary == 'multipart/alternative':
                # for HTML emails, the multipart/alternative part contains the HTML and its alternative text representation
                # BUT it seems that plenty of messages add file attachments after the txt and html, so we'll have to account for that
                if part.get_content_type() == 'text/plain' and alternativetextplainfound == False:
                    alternativetextplainfound = True
                    continue
                if part.get_content_type() == 'text/html' and alternativetexthtmlfound == False:
                    alternativetexthtmlfound = True
                    continue
            if (part.get_content_type() == 'text/plain') and (lastseenboundary != 'multipart/alternative'):
                # if this is a plain text email, then the first txt attachment is the message body so we do not
                # count it as an attachment
                if firsttextattachmentseen == False:
                    firsttextattachmentseen = True
                    continue
                else:
                    totalattachments += 1
                    continue
            # any other part we encounter we shall assume is a user added attachment
            totalattachments += 1
        return totalattachments


def startBackup(parameters: tuple):
    mail: SaveMails = parameters[0]
    progress: ProgressWindow = parameters[1]
    mail.backupMails(progress)
    progress.window.destroy()


if __name__ == '__main__':
    mail = SaveMails()
    progressWindow = ProgressWindow('Mail Backup')
    progressWindow.addButtonWithFunction(
        'Backup Now', startBackup, (mail, progressWindow))
    progressWindow.runGUI()
