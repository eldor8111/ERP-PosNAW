import requests
import itertools

email = "supergeroy2580@gmail.com"
url = "https://notify.eskiz.uz/api/auth/login"

# Ambiguous parts
# ajjg1m{0/O}DagelnulNNXk635Ek4tYOYTC5xvp39eGR
# Dagelnul or Dagelnui or DagelnuI ?
# YOYTC or YOYtC ?

c1 = ['0', 'O']
c2 = ['l', 'I', 'i']
c3 = ['T', 't']

print("Testing combinations...")
for a in c1:
    for b in c2:
        for c in c3:
            password = f"ajjg1m{a}DagelnulNNXk635Ek4tYOY{c}C5xvp39eGR".replace('l', b, 1) # wait, two 'l's in elnul
            # Actually let's just replace the specific char: Dagelnu{b}
            password = f"ajjg1m{a}Dagelnu{b}NNXk635Ek4tYOY{c}C5xvp39eGR"
            try:
                resp = requests.post(url, data={"email": email, "password": password})
                if resp.status_code == 200:
                    print("SUCCESS! Password is:", password)
                    exit(0)
            except Exception as e:
                pass

print("None worked.")
