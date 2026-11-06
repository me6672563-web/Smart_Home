person = ["menna", "atef", "fathy" ,"nada"]

def check(name, option="yes"):
    ask = name.strip().lower()
    option = option.lower()
    for i in person:
        if ask == i:
            messages = ["welcome " + i]
            if option == "yes":
                messages.append("door is opening")
            else:
                messages.append("door is not opening")
            return {"known": True, "name": i, "open": option == "yes", "messages": messages}
    return {"known": False, "name": ask, "open": False,
            "messages": ["please wait to ask my owner"]}


if __name__ == "__main__":
    ask = input("who are you? ").lower()
    option = input("do you want to open the door? (yes or no) ").lower()
    for line in check(ask, option)["messages"]:
        print(line)