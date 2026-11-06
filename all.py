from experta import Fact, KnowledgeEngine, Rule ,P

class HomeFacts(Fact):
    pass

temperature =int(input("Enter the temperature: "))
name = input("Enter your name: ").lower()
ask_tv=input("Do you want to still tevision on? : ").lower()

class SmartHome(KnowledgeEngine):
    
    #lights
    @Rule(HomeFacts(person=True))
    def turn_on_lights(self):
            print("Lights: ON")
        
    @Rule(HomeFacts(person=False))
    def turn_off_lights(self):
            print("Lights: OFF")
            
    #air conditioner
    @Rule(HomeFacts(person=True ,temperature=P(lambda x: x > 25)))
    def turn_on_ac(self):
        print("Air Conditioner: ON")

    @Rule(HomeFacts(person=False,temperature=P(lambda x: x <= 25)))
    def turn_off_ac(self):
        print("Air Conditioner: OFF")
    
    #door lock
    @Rule(HomeFacts(name=P(lambda x: x in ["menna", "atef", "fathy"])))
    def open_door(self):
        print("Door Lock: OPEN")

    @Rule(HomeFacts(name=P(lambda x: x not in ["menna", "atef", "fathy"])))
    def close_door(self):
        print("Door Lock: CLOSED")
        
    #tevision
    @Rule(HomeFacts(person=True ,ask_tv="yes"))
    def turn_on_tv(self):
        print("Tevision: ON")
    
    @Rule(HomeFacts(person=False ,ask_tv="no"))
    def turn_off_tv(self):
        print("Tevision: OFF")
        
    
    