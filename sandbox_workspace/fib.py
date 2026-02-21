def fibonacci_up_to(limit):
    a, b = 0, 1
    while a <= limit:
        print(a)
        a, b = b, a + b


if __name__ == "__main__":
    fibonacci_up_to(100)
