from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.testclient import TestClient

app = FastAPI()

class Resp(BaseModel): 
    x: str

@app.get('/', response_model=Resp)
def f(): 
    raise HTTPException(202, detail={'a':1})
    
client=TestClient(app)
print(client.get('/').json())
