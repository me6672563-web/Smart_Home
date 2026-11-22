CHANNELS = ["mbc masr", "mbc masr2", "cbc", "cbc drama", "dmc", "dmc drama", "rotana", "rotana cinema", "rotana classic"]
CURRENT_VOLUME = 10
MAX_VOLUME = 100


def turn_on(ask, channel=None):
    if ask.lower() == "yes":
        return {"on": True, "channel": channel,
                "messages": ["Turning on the TV...", f"Switching to channel {channel}..."]}
    return {"on": False, "channel": None, "messages": ["okey"]}


def channel_not_found_message():
    return "this channel is not available"


def volume_message(current, new):
    return f"Volume changed from {current} to {new}"


def ask_channel():
    while True:
        channel = input("Which channel would you like to watch? ").strip().lower()
        if channel in CHANNELS:
            return channel
        print(channel_not_found_message())
        print("Available channels:", ", ".join(CHANNELS))


def ask_volume(current):
    ask = input("Do you want to change the volume? (yes/no): ")
    if ask.lower() != "yes":
        return current

    print(f"Current volume is {current}")
    while True:
        try:
            new_volume = int(input(f"Enter the new volume (0-{MAX_VOLUME}): "))
        except ValueError:
            print("Please enter a valid integer")
            continue

        if new_volume < 0 or new_volume > MAX_VOLUME:
            print(f"Volume must be between 0 and {MAX_VOLUME}")
        else:
            print(volume_message(current, new_volume))
            return new_volume


if __name__ == "__main__":
    ask = input("Do you want to turn on the TV? (yes/no): ")
    channel = None
    if ask.lower() == "yes":
        channel = ask_channel()
    for line in turn_on(ask, channel)["messages"]:
        print(line)

    if ask.lower() == "yes":
        volume = ask_volume(CURRENT_VOLUME)