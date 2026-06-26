import re
#from datetime import date
#from dateutil.parser import parse

def normalize(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text

def sentences(text):
    return re.split(r'(?<=[.!?])\s+', text)