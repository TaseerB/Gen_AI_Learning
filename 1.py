def count_up(n):
    for i in range(n):
        yield i


for num in count_up(3):
    print(num)