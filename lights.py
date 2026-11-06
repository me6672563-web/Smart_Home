def decide(person):
    if person == True:
        return "ON"
    return "OFF"


def keep(ask):
    if ask.lower() == "yes":
        return "ON"
    return "OFF"


if __name__ == "__main__":
    person = True
    lights = decide(person)
    ask = input("Do you want lights still ON? (yes/no): ")
    lights = keep(ask)
    print("Lights:", lights)