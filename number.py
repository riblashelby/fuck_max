from pathlib import Path
p = Path("config/number")
number = int(input('Номер телефона(без +7): '))
if len(number) != 10:
    print('Номер должен состоять из мин. 10 чисел без пробелов дефисов и тд')    
else:
    if p.exists():
        confirm = input("Файл уже существует. Перезаписать? (y/n): ").lower()
        if confirm != "y":
            print("Отмена. Файл не изменён.")
            exit()
    p.write_text(str(number), encoding="utf-8")
    print("Данные успешно сохранены в", p)          