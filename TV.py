def turn_on(ask, channel=None):
    if ask.lower() == "yes":
        return {"on": True, "channel": channel,
                "messages": ["Turning on the TV...", f"Switching to channel {channel}..."]}
    return {"on": False, "channel": None, "messages": ["okey"]}


if __name__ == "__main__":
    ask = input("Do you want to turn on the TV? (yes/no): ")
    channel = None
    if ask.lower() == "yes":
        channel = input("Which channel would you like to watch? ")
    for line in turn_on(ask, channel)["messages"]:
        print(line)