
from tkinter import *
from tkinter.ttk import *
from tkinter import Button,Frame,Label, messagebox
import threading
import comtypes.client


class FrameLogin(Frame):
    def __init__(self, master = None):
        Frame.__init__(self, master)
        self.grid()
        self.place()
        self.FrameLogin = Frame(self)
        self.master["background"] = "#F5F5F5"
        self.FrameLogin.master["background"] = "#F5F5F5" 
        self.createWidgets()

        self.win_lock = threading.Lock()

    def createWidgets(self):
        self.gen_dir_text = Label(self)
        self.gen_dir_text['text'] = f"Gen Dir: {comtypes.client.gen_dir}"
        self.gen_dir_text.grid(column = 0, row = 0,sticky= W)

        self.status_text = Label(self, text='starting...', fg='orange')
        self.status_text.grid(column=0, row=3, sticky=W)
        self.os_status_text = Label(self, text='starting...', fg='orange')
        self.os_status_text.grid(column=0, row=4, sticky=W)

        self.symbol_display = Listbox(self)
        self.symbol_display.grid(column = 0, row = 5,sticky= W)

    def change_status(self, text, color):
        self.win_lock.acquire()
        self.status_text['text'] = text
        self.status_text['fg'] = color
        self.win_lock.release()

    def os_change_status(self, text, color):
        self.win_lock.acquire()
        self.os_status_text['text'] = text
        self.os_status_text['fg'] = color
        self.win_lock.release()

    def add_symbol(self, symbol):
        self.win_lock.acquire()
        self.symbol_display.insert(END, symbol)
        self.win_lock.release()
