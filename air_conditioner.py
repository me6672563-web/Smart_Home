ON_TEMP = 25
MAX_TEMP = 30


def decide(person, temperature):
    if person == True and temperature >= ON_TEMP:
        return "ON"
    return "OFF"


def changed_message(new_temp):
    return f"Temperature changed to {new_temp}°C"


def keep_message():
    return "Temperature remains the same."


def too_high_message():
    return f"The highest temperature setting for the air conditioner is {MAX_TEMP}°C"


if __name__ == "__main__":
    person = True
    temperature = 30
    air_conditioner = decide(person, temperature)
    if air_conditioner == "ON":
        ask = input("Do you want to change the temperature? (yes/no): ")
        if ask.lower() == "yes":
            while True:
                try:
                    new_temp = int(input("Enter the new temperature: "))
                except ValueError:
                    print("Please enter a valid integer")
                    continue

                if new_temp > MAX_TEMP:
                    print(too_high_message())
                else:
                    temperature = new_temp
                    print(changed_message(temperature))
                    break
        else:
            print(keep_message())