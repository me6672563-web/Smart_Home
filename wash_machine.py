def start(ask, wash_type=None):
    if ask.lower() == "yes":
        messages = ["Washing machine is ON"]
        wt = (wash_type or "").lower()
        if wt == "normal":
            messages.append("Normal wash selected")
        elif wt == "quick":
            messages.append("Quick wash selected")
        else:
            messages.append("Invalid wash type")
        return {"on": True, "wash_type": wt, "valid": wt in ("normal", "quick"),
                "messages": messages}
    return {"on": False, "wash_type": None, "valid": False,
            "messages": ["Washing machine is OFF"]}


if __name__ == "__main__":
    ask = input("Do you want to turn on the washing machine? (yes/no): ")
    wash_type = None
    if ask.lower() == "yes":
        wash_type = input("Choose wash type (normal/quick): ")
    for line in start(ask, wash_type)["messages"]:
        print(line)