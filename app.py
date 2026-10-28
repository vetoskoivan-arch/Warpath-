import csv
import json
import os
import re
import shutil
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageGrab, ImageOps, ImageEnhance, ImageTk
import pytesseract

APP_NAME = 'Warpath Inventory'
DATA_DIR = Path(os.environ.get('APPDATA', str(Path.home()))) / 'WarpathInventory'
DATA_FILE = DATA_DIR / 'inventory.json'
CATEGORIES = ['Ресурсы', 'Ускорения', 'Купоны и валюты', 'Материалы', 'Фрагменты', 'Предметы', 'Другое']


def tesseract_path():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    bundled = base / 'tesseract' / 'tesseract.exe'
    if bundled.exists():
        pytesseract.pytesseract.tesseract_cmd = str(bundled)
        os.environ['TESSDATA_PREFIX'] = str(base / 'tesseract' / 'tessdata')
    elif shutil.which('tesseract'):
        pytesseract.pytesseract.tesseract_cmd = shutil.which('tesseract')
    else:
        raise RuntimeError('Не найден движок Tesseract OCR. Используйте установочную сборку.')


def ocr_image(image):
    tesseract_path()
    im = ImageOps.grayscale(image)
    im = ImageEnhance.Contrast(im).enhance(1.8)
    im = im.resize((im.width * 2, im.height * 2))
    try:
        raw = pytesseract.image_to_string(im, lang='rus+eng', config='--psm 11')
    except pytesseract.TesseractError:
        raw = pytesseract.image_to_string(im, lang='eng', config='--psm 11')
    candidates = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        for match in re.finditer(r'(?<!\w)(\d[\d\s.,]*\d|\d+)\s*([KkКкMmМмBbВв]?)\b', line):
            token, suffix = match.group(1), match.group(2)
            number = token.replace(' ', '').replace(',', '.')
            try:
                if suffix:
                    val = int(float(number) * {'k': 1000, 'к': 1000, 'm': 1000000, 'м': 1000000, 'b': 1000000000, 'в': 1000000000}[suffix.lower()])
                else:
                    val = int(number.replace('.', ''))
                if val > 0:
                    candidates.append((line[:90], val))
            except (ValueError, KeyError):
                continue
    return raw, candidates


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME + ' — Windows')
        self.root.geometry('1060x740')
        self.root.minsize(850, 580)
        self.items = []
        self.candidates = []
        self.image = None
        self.preview_ref = None
        self.status = tk.StringVar(value='Готово. Загрузите скриншот или захватите экран.')
        self.name = tk.StringVar()
        self.amount = tk.StringVar()
        self.category = tk.StringVar(value=CATEGORIES[0])
        self.build()
        self.load()

    def build(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='WARPATH INVENTORY', font=('Segoe UI', 19, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Локальный учёт имущества · OCR-подсказки требуют проверки').pack(anchor='w')
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill='x', pady=10)
        ttk.Button(toolbar, text='Открыть скриншоты', command=self.open_images).pack(side='left', padx=(0, 7))
        ttk.Button(toolbar, text='Захватить экран', command=self.capture).pack(side='left', padx=(0, 7))
        ttk.Button(toolbar, text='Экспорт CSV', command=self.export_csv).pack(side='left', padx=(0, 7))
        ttk.Button(toolbar, text='Очистить инвентарь', command=self.clear).pack(side='right')
        split = ttk.PanedWindow(outer, orient='horizontal')
        split.pack(fill='both', expand=True)
        left = ttk.Frame(split, padding=4)
        right = ttk.Frame(split, padding=4)
        split.add(left, weight=2)
        split.add(right, weight=3)
        self.preview = ttk.Label(left, text='Предпросмотр скриншота', anchor='center', relief='solid')
        self.preview.pack(fill='both', expand=True)
        ttk.Label(left, text='Распознанные строки и числа (не подтверждены):').pack(anchor='w', pady=(10, 4))
        self.candidate_list = tk.Listbox(left, height=9, exportselection=False)
        self.candidate_list.pack(fill='x')
        self.candidate_list.bind('<<ListboxSelect>>', self.select_candidate)
        ttk.Label(right, text='Добавить / подтвердить имущество', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        form = ttk.Frame(right)
        form.pack(fill='x', pady=8)
        ttk.Label(form, text='Название предмета').grid(row=0, column=0, sticky='w')
        ttk.Entry(form, textvariable=self.name).grid(row=1, column=0, sticky='ew', padx=(0, 8))
        ttk.Label(form, text='Количество').grid(row=0, column=1, sticky='w')
        ttk.Entry(form, textvariable=self.amount, width=13).grid(row=1, column=1, sticky='ew')
        ttk.Label(form, text='Категория').grid(row=2, column=0, sticky='w', pady=(8, 0))
        ttk.Combobox(form, textvariable=self.category, values=CATEGORIES, state='readonly').grid(row=3, column=0, sticky='ew', padx=(0, 8))
        ttk.Button(form, text='Добавить в инвентарь', command=self.add_item).grid(row=3, column=1, sticky='ew')
        form.columnconfigure(0, weight=1)
        ttk.Label(right, text='Подтверждённый инвентарь', font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(10, 5))
        cols = ('category', 'name', 'amount')
        self.tree = ttk.Treeview(right, columns=cols, show='headings', selectmode='extended')
        for c, heading, width in [('category', 'Категория', 115), ('name', 'Название', 180), ('amount', 'Количество', 105)]:
            self.tree.heading(c, text=heading)
            self.tree.column(c, width=width, stretch=True)
        self.tree.pack(fill='both', expand=True)
        ttk.Button(right, text='Удалить выделенные строки', command=self.remove_selected).pack(anchor='e', pady=7)
        ttk.Label(outer, textvariable=self.status, anchor='w').pack(fill='x', pady=(7, 0))

    def open_images(self):
        paths = filedialog.askopenfilenames(title='Скриншоты Warpath', filetypes=[('Изображения', '*.png *.jpg *.jpeg *.bmp *.webp')])
        if paths:
            self.process_paths(list(paths))

    def capture(self):
        self.root.iconify()
        self.root.after(700, self._capture_now)

    def _capture_now(self):
        try:
            im = ImageGrab.grab(all_screens=True)
            self.root.deiconify()
            self.process_image(im, 'Захват экрана')
        except Exception as exc:
            self.root.deiconify()
            messagebox.showerror('Ошибка захвата', str(exc))

    def process_paths(self, paths):
        self.status.set(f'Обработка файлов: {len(paths)}…')
        def worker():
            result = []
            last = None
            errors = []
            for path in paths:
                try:
                    with Image.open(path) as im:
                        pic = im.convert('RGB')
                    raw, found = ocr_image(pic)
                    result.extend([(Path(path).name + ': ' + s, n) for s, n in found])
                    last = pic
                except Exception as exc:
                    errors.append(f'{Path(path).name}: {exc}')
            self.root.after(0, lambda: self.finish_scan(last, result, errors))
        threading.Thread(target=worker, daemon=True).start()

    def process_image(self, im, label):
        self.status.set('Распознавание захваченного экрана…')
        def worker():
            try:
                _, found = ocr_image(im)
                self.root.after(0, lambda: self.finish_scan(im, [(label + ': ' + s, n) for s, n in found], []))
            except Exception as exc:
                self.root.after(0, lambda: self.finish_scan(im, [], [str(exc)]))
        threading.Thread(target=worker, daemon=True).start()

    def finish_scan(self, im, found, errors):
        if im is not None:
            self.image = im
            im = im.copy()
            im.thumbnail((420, 350))
            self.preview_ref = ImageTk.PhotoImage(im)
            self.preview.configure(image=self.preview_ref, text='')
        self.candidates = found
        self.candidate_list.delete(0, tk.END)
        for line, n in found:
            self.candidate_list.insert(tk.END, f'{n:,} | {line}')
        self.status.set(f'Найдено числовых подсказок: {len(found)}. Проверьте название и количество перед добавлением.')
        if errors:
            messagebox.showwarning('Часть файлов не обработана', '\n'.join(errors[:8]))

    def select_candidate(self, _event=None):
        selected = self.candidate_list.curselection()
        if selected:
            line, n = self.candidates[selected[0]]
            self.name.set(re.sub(r'\d[\d\s.,]*\s*[KkКкMmМмBbВв]?', '', line.split(': ', 1)[-1]).strip(' -:|')[:100])
            self.amount.set(str(n))

    def add_item(self):
        name = self.name.get().strip()
        try:
            amount = int(self.amount.get().replace(' ', '').replace(',', ''))
            if amount < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror('Ошибка', 'Количество должно быть целым неотрицательным числом.')
            return
        if not name:
            messagebox.showerror('Ошибка', 'Введите название предмета.')
            return
        for item in self.items:
            if item['name'].casefold() == name.casefold() and item['category'] == self.category.get():
                if messagebox.askyesno('Обновить запись?', 'Предмет уже существует. Заменить его количество?'):
                    item['amount'] = amount
                    self.refresh()
                    self.save()
                return
        self.items.append({'category': self.category.get(), 'name': name, 'amount': amount})
        self.refresh()
        self.save()
        self.name.set('')
        self.amount.set('')

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, item in enumerate(self.items):
            self.tree.insert('', 'end', iid=str(i), values=(item['category'], item['name'], f"{item['amount']:,}"))
        self.status.set(f'Сохранено записей: {len(self.items)} · {DATA_FILE}')

    def remove_selected(self):
        for idx in sorted((int(x) for x in self.tree.selection()), reverse=True):
            del self.items[idx]
        self.refresh()
        self.save()

    def clear(self):
        if messagebox.askyesno('Очистка', 'Удалить все сохранённые записи инвентаря?'):
            self.items = []
            self.refresh()
            self.save()

    def load(self):
        try:
            if DATA_FILE.exists():
                data = json.loads(DATA_FILE.read_text(encoding='utf-8'))
                self.items = data if isinstance(data, list) else []
            self.refresh()
        except Exception as exc:
            messagebox.showwarning('Ошибка загрузки', str(exc))

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = DATA_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(DATA_FILE)

    def export_csv(self):
        if not self.items:
            messagebox.showinfo('Экспорт', 'Инвентарь пока пуст.')
            return
        dest = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='warpath_inventory.csv', filetypes=[('CSV', '*.csv')])
        if dest:
            with open(dest, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['category', 'name', 'amount'], delimiter=';')
                writer.writeheader()
                writer.writerows(self.items)
            messagebox.showinfo('Экспорт', 'CSV сохранён.')


if __name__ == '__main__':
    root = tk.Tk()
    try:
        ttk.Style().theme_use('vista' if sys.platform == 'win32' else 'clam')
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
