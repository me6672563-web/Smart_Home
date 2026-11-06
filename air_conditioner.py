ON_TEMP = 25

def decide(person, temperature):
    if person == True and temperature >= ON_TEMP:
        return "ON"
    return "OFF"


def changed_message(new_temp):
    return f"Temperature changed to {new_temp}°C"


def keep_message():
    return "Temperature remains the same."


if __name__ == "__main__":
    person = True
    temperature = 30
    air_conditioner = decide(person, temperature)
    if air_conditioner == "ON":
        ask = input("Do you want to change the temperature? (yes/no): ")
        if ask.lower() == "yes":
            new_temp = int(input("Enter the new temperature: "))
            temperature = new_temp
            print(changed_message(temperature))
        else:
            print(keep_message())