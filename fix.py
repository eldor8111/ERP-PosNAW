import sys, re
with open('app/routers/payme.py', 'rb') as f:
    text = f.read().decode('utf-8')
text = re.sub(r"([a-zA-Z])'([a-zA-Z])", r"\1\2", text)
with open('app/routers/payme.py', 'wb') as f:
    f.write(text.encode('utf-8'))
