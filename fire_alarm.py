TEMP_LIMIT = 30  

def is_on(ask, temperature):
    return ask.lower() == "yes" or temperature >= TEMP_LIMIT


def check(ask, temperature):
    if is_on(ask, temperature):
        return "Fire Alarm: ON"
    return "Fire Alarm: Off"


if __name__ == "__main__":
    ask = input("Is there somke or a increase in the temperature?(yes / no):").lower()
    temperature = int(input("Enter the temperature:"))
    print(check(ask, temperature))