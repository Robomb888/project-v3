import re
#from datetime import date
#from dateutil.parser import parse

def normalize(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text
 
def sentences(text):
    # split on sentence punctuation OR line breaks; drop blanks
    parts = re.split(r'(?<=[.!?])\s+|\n+', text)
    return [p.strip() for p in parts if p and p.strip()]