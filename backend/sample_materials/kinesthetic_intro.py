# Number Base System - Interactive Lab
def decimal_to_binary(n):
    return bin(n)[2:]

print("Welcome to the Kinesthetic Lab!")
while True:
    try:
        num = int(input("Enter a decimal number (or -1 to quit): "))
        if num == -1: break
        print(f"Binary representation: {decimal_to_binary(num)}")
    except:
        print("Please enter a valid integer.")
