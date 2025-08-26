from pathlib import Path
p = Path("config/cooldown")
cd = int(input('Введите время между проверками в секундах: '))
    
if p.exists():
    confirm = input("Файл уже существует. Перезаписать? (y/n): ").lower()
    if confirm != "y":
        print("Отмена. Файл не изменён.")
        exit()
    p.write_text(str(cd), encoding="utf-8")
    print("Данные успешно сохранены в", p)