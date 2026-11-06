password = 2007

def check(entered):
    try:
        value = int(str(entered).strip())
    except ValueError:
        value = None
    if value == password:
        return {"ok": True, "message": "welcome home"}
    return {"ok": False, "message": "Incorrect password"}


if __name__ == "__main__":
    check_password = input("Please,enter security password:")
    print(check(check_password)["message"])