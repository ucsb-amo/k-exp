import os

DATA_DIR = os.getenv("data")
RUN_ID_PATH = os.path.join(DATA_DIR,"run_id.py")

def update_run_id():
    pwd = os.getcwd()
    os.chdir(DATA_DIR)
    with open(RUN_ID_PATH,'r') as f:
        rid = int(f.read())
    with open(RUN_ID_PATH,'w') as f:
        line = f"{rid+1}"
        f.write(line)
    os.chdir(pwd)

if __name__ == "__main__":
    update_run_id()