import sys
import traceback
import codecs
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import rubymarshal
import rubymarshal.reader
import rubymarshal.writer
import rubymarshal.classes

# =========================================================
# 1. 출력 리다이렉션 (GUI 콘솔 모니터용)
# =========================================================
class RedirectText(object):
    def __init__(self, text_widget):
        self.output = text_widget
        
    def write(self, string):
        self.output.insert(tk.END, string)
        self.output.see(tk.END)
        
    def flush(self):
        pass

# =========================================================
# 2. rubymarshal 라이브러리 통합 버그 패치
# =========================================================

# [패치 1] 읽기 에러 우회 (순환 참조)
original_read = rubymarshal.reader.Reader.read
def patched_read(self, *args, **kwargs):
    try:
        return original_read(self, *args, **kwargs)
    except ValueError as e:
        if "invalid link destination" in str(e):
            return f"<Link Error Bypassed>"
        raise
rubymarshal.reader.Reader.read = patched_read

# [패치 2] 인코딩 읽기 에러 우회
def patched_get_encoding(*args, **kwargs):
    attrs = args[-1] if args else {}
    if not isinstance(attrs, dict): return "utf-8"
    enc_str = "utf-8"
    if "encoding" in attrs:
        enc = attrs["encoding"]
        if hasattr(enc, "text"): enc_str = str(enc.text)
        elif isinstance(enc, bytes): enc_str = enc.decode('utf-8', errors='ignore')
        else: enc_str = str(enc)
    try:
        codecs.lookup(enc_str)
        return enc_str
    except LookupError:
        return "utf-8"
rubymarshal.reader.Reader._get_encoding = patched_get_encoding

# [패치 3] 쓰기 시 RubyString 인코딩 충돌 우회
def safe_ruby_string_encode(self, encoding="utf-8", errors="strict"):
    text_val = getattr(self, 'text', '')
    if isinstance(text_val, bytes):
        return text_val
    try:
        if not encoding: encoding = "utf-8"
        return text_val.encode(encoding, errors)
    except (LookupError, TypeError, ValueError):
        return str(text_val).encode('utf-8', errors='ignore')
rubymarshal.classes.RubyString.encode = safe_ruby_string_encode

# ★ [핵심 패치 4] 쓰기 시 파이썬 Tuple -> 루비 Array(List) 자동 변환
original_writer_write = rubymarshal.writer.Writer.write
def patched_writer_write(self, obj):
    # 파이썬 딕셔너리 키로 사용된 튜플을 다시 리스트(루비 배열)로 변환 후 저장
    if isinstance(obj, tuple):
        obj = list(obj)
    return original_writer_write(self, obj)
rubymarshal.writer.Writer.write = patched_writer_write


# =========================================================
# 3. GUI 세이브 에디터 앱
# =========================================================
class SaveEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("포켓몬 세이브 데이터 에디터 (수정/저장 및 로그 모니터)")
        self.root.geometry("1100x800")
        
        self.node_mapping = {}
        self.current_data = None 

        top_frame = tk.Frame(self.root, pady=10, padx=10)
        top_frame.pack(side="top", fill="x")

        self.load_btn = tk.Button(
            top_frame, text="📁 세이브 불러오기", font=("맑은 고딕", 10, "bold"), command=self.load_file
        )
        self.load_btn.pack(side="left")

        self.save_btn = tk.Button(
            top_frame, text="💾 수정된 세이브 저장하기", font=("맑은 고딕", 10, "bold"), 
            command=self.save_file, state="disabled", fg="blue"
        )
        self.save_btn.pack(side="left", padx=10)
        
        self.status_label = tk.Label(top_frame, text="파일을 불러와주세요.", fg="gray")
        self.status_label.pack(side="left", padx=15)

        log_frame = tk.LabelFrame(self.root, text="시스템 로그 모니터 (System Log)", padx=5, pady=5)
        log_frame.pack(side="bottom", fill="x", padx=10, pady=10)

        self.copy_log_btn = tk.Button(log_frame, text="📋 로그 전체 복사", command=self.copy_log_to_clipboard)
        self.copy_log_btn.pack(side="right", padx=5, fill="y")

        self.log_text = tk.Text(log_frame, height=8, bg="black", fg="lightgreen", font=("Consolas", 10))
        log_vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        
        log_vsb.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

        sys.stdout = RedirectText(self.log_text)
        sys.stderr = RedirectText(self.log_text)

        tree_frame = tk.Frame(self.root)
        tree_frame.pack(side="top", fill="both", expand=True, padx=10)

        columns = ("Type", "Value", "Path")
        self.tree = ttk.Treeview(tree_frame, columns=columns)
        
        self.tree.heading("#0", text="이름 (Name / Key)")
        self.tree.heading("Type", text="데이터 타입 (Type)")
        self.tree.heading("Value", text="값 (Value)")
        self.tree.heading("Path", text="경로 (Path)")
        
        self.tree.column("#0", width=250, anchor='w')
        self.tree.column("Type", width=150, anchor='w')
        self.tree.column("Value", width=250, anchor='w')
        self.tree.column("Path", width=400, anchor='w')

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.tree.pack(side='left', fill='both', expand=True)

        self.tree.bind("<Double-1>", self.on_double_click)
        
        print("포켓몬 세이브 데이터 에디터가 시작되었습니다.")
        print("모든 시스템 로그와 에러 메시지는 이곳에 표시됩니다.\n")

    def copy_log_to_clipboard(self):
        log_content = self.log_text.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(log_content)
        messagebox.showinfo("알림", "로그 내용이 클립보드에 복사되었습니다.")

    def auto_copy_error(self, error_msg):
        self.root.clipboard_clear()
        self.root.clipboard_append(error_msg)

    def load_file(self):
        file_path = filedialog.askopenfilename(
            title="세이브 파일 선택",
            filetypes=[("RPG Maker Save", "*.rxdata"), ("All Files", "*.*")]
        )
        if not file_path: return

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.node_mapping.clear()
        self.save_btn.config(state="disabled")

        self.root.title(f"포켓몬 세이브 에디터 - {file_path}")
        self.status_label.config(text="데이터를 읽고 렌더링하는 중입니다...", fg="blue")
        self.root.update()

        try:
            with open(file_path, 'rb') as f:
                print(f"[{file_path}] 파일 로딩 중...")
                self.current_data = rubymarshal.reader.load(f)
                
            self.insert_node("", self.current_data, name="SaveData", path="root0", parent_obj=None, parent_key=None)
            
            self.status_label.config(text="로드 완료! 값을 수정하려면 더블클릭하세요.", fg="green")
            self.save_btn.config(state="normal")
            print("✅ 렌더링이 완료되었습니다.")
            
        except Exception as e:
            error_msg = traceback.format_exc()
            print("\n🚨 파일을 읽는 도중 오류가 발생했습니다:\n" + error_msg)
            self.auto_copy_error(error_msg)
            messagebox.showerror("오류 발생", f"파일 로드 실패! 에러 로그가 클립보드에 복사되었습니다.\n\n{e}")
            self.status_label.config(text="파일 로드 실패", fg="red")

    def insert_node(self, parent_id, data, name="root", path="root", parent_obj=None, parent_key=None):
        dtype = type(data).__name__
        value_str = ""
        
        is_ruby_string = (dtype == 'RubyString') or hasattr(data, 'text')
        is_primitive = isinstance(data, (int, float, str, bytes, bool)) or is_ruby_string

        if is_ruby_string:
            raw_data = data.text if hasattr(data, 'text') else data
            if isinstance(raw_data, bytes):
                try: 
                    value_str = raw_data.decode('utf-8')
                except UnicodeDecodeError: 
                    value_str = raw_data.decode('cp949', errors='ignore')
            else:
                value_str = str(raw_data)
                
            display_str = value_str[:97] + "..." if len(value_str) > 100 else value_str
            node_id = self.tree.insert(parent_id, 'end', text=str(name), values=("RubyString (Text)", display_str, path))
            
            if hasattr(data, 'attributes'):
                new_base_path = f"{path}@rb:attributes"
                for key, val in data.attributes.items():
                    key_name = str(getattr(key, 'name', key))
                    self.insert_node(node_id, val, name=key_name, path=f"{new_base_path}{key_name}", parent_obj=data, parent_key=key)

        elif isinstance(data, rubymarshal.classes.RubyObject):
            class_name = "UnknownClass"
            if hasattr(data, 'class_symbol'): class_name = str(getattr(data.class_symbol, 'name', data.class_symbol))
            elif hasattr(data, 'sym'): class_name = str(getattr(data.sym, 'name', data.sym))
            
            value_str = f"Ruby Object ({class_name})"
            node_id = self.tree.insert(parent_id, 'end', text=str(name), values=(dtype, value_str, path))
            
            if hasattr(data, 'attributes'):
                new_base_path = f"{path}@rb:attributes"
                for key, val in data.attributes.items():
                    key_name = str(getattr(key, 'name', key))
                    self.insert_node(node_id, val, name=key_name, path=f"{new_base_path}{key_name}", parent_obj=data, parent_key=key)

        elif isinstance(data, dict):
            value_str = f"Hash (크기: {len(data)})"
            node_id = self.tree.insert(parent_id, 'end', text=str(name), values=(dtype, value_str, path))
            for key, val in data.items():
                key_name = str(getattr(key, 'name', key))
                self.insert_node(node_id, val, name=key_name, path=f"{path}{key_name}", parent_obj=data, parent_key=key)

        elif isinstance(data, list):
            value_str = f"Array (크기: {len(data)})"
            node_id = self.tree.insert(parent_id, 'end', text=str(name), values=(dtype, value_str, path))
            for i in range(len(data)):
                self.insert_node(node_id, data[i], name=f"Index[{i}]", path=f"{path}{i}", parent_obj=data, parent_key=i)

        elif isinstance(data, rubymarshal.classes.Symbol):
            value_str = f":{data.name}"
            node_id = self.tree.insert(parent_id, 'end', text=str(name), values=("Symbol", value_str, path))

        else:
            if isinstance(data, bytes):
                try: 
                    value_str = data.decode('utf-8')
                except UnicodeDecodeError: 
                    value_str = data.decode('cp949', errors='ignore')
            else:
                value_str = str(data)
                
            display_str = value_str[:97] + "..." if len(value_str) > 100 else value_str
            node_id = self.tree.insert(parent_id, 'end', text=str(name), values=(dtype, display_str, path))

        self.node_mapping[node_id] = {
            'parent_obj': parent_obj,
            'parent_key': parent_key,
            'data_type': type(data),
            'original_data': data,
            'is_primitive': is_primitive,
            'is_ruby_string': is_ruby_string
        }

    def on_double_click(self, event):
        selected = self.tree.selection()
        if not selected: return
        node_id = selected[0]
        
        mapping = self.node_mapping.get(node_id)
        if not mapping or mapping['parent_obj'] is None: return

        target_type = mapping['data_type']
        is_ruby_string = mapping['is_ruby_string']
        
        if not mapping['is_primitive']:
            messagebox.showinfo("안내", "이 항목은 배열이나 객체 구조이므로 직접 값을 수정할 수 없습니다.\n하위 항목을 열어서 세부 값을 수정해 주세요.")
            return

        current_val = mapping['original_data']
        
        if is_ruby_string:
            raw_data = current_val.text if hasattr(current_val, 'text') else current_val
            if isinstance(raw_data, bytes):
                try: current_val_str = raw_data.decode('utf-8')
                except: current_val_str = raw_data.decode('cp949', errors='ignore')
            else:
                current_val_str = str(raw_data)
        elif target_type == bytes:
            try: current_val_str = current_val.decode('utf-8')
            except: current_val_str = current_val.decode('cp949', errors='ignore')
        else:
            current_val_str = str(current_val)

        type_label = "RubyString (Text)" if is_ruby_string else target_type.__name__
        new_val_str = simpledialog.askstring("값 수정", f"새로운 값을 입력하세요 ({type_label}):", initialvalue=current_val_str)

        if new_val_str is not None:
            try:
                if target_type == int: new_val = int(new_val_str)
                elif target_type == float: new_val = float(new_val_str)
                elif target_type == bool: new_val = new_val_str.lower() in ('true', '1', 't', 'y', 'yes')
                elif target_type == bytes: new_val = new_val_str.encode('utf-8')
                elif is_ruby_string:
                    if hasattr(current_val, 'text'):
                        current_val.text = new_val_str
                    else:
                        current_val = new_val_str
                    new_val = current_val 
                else: new_val = new_val_str 
                
                if not (is_ruby_string and hasattr(mapping['original_data'], 'text')):
                    parent = mapping['parent_obj']
                    key = mapping['parent_key']

                    if isinstance(parent, rubymarshal.classes.RubyObject):
                        parent.attributes[key] = new_val
                    elif isinstance(parent, dict):
                        parent[key] = new_val
                    elif isinstance(parent, list):
                        parent[key] = new_val

                    mapping['original_data'] = new_val

                display_val = str(new_val_str)
                if len(display_val) > 100: display_val = display_val[:97] + "..."
                
                current_values = list(self.tree.item(node_id, "values"))
                current_values[1] = display_val
                self.tree.item(node_id, values=current_values)

                print(f"[수정됨] 경로: {self.tree.item(node_id, 'values')[2]} | 기존값: {current_val_str} -> 새 값: {new_val_str}")
                self.status_label.config(text="값이 메모리에 반영되었습니다. 완료 후 꼭 '저장' 버튼을 누르세요.", fg="blue")

            except ValueError:
                print(f"🚨 입력 오류: 올바른 {target_type.__name__} 형식이 아닙니다. 입력값: {new_val_str}")
                messagebox.showerror("입력 오류", f"입력하신 값이 올바른 {target_type.__name__} 형식이 아닙니다.")

    def save_file(self):
        if not self.current_data:
            return
            
        save_path = filedialog.asksaveasfilename(
            title="수정된 세이브 파일 저장",
            defaultextension=".rxdata",
            initialfile="Save_Edited.rxdata",
            filetypes=[("RPG Maker Save", "*.rxdata"), ("All Files", "*.*")]
        )
        if not save_path: return

        try:
            print(f"\n[저장 중] {save_path} 파일에 데이터를 쓰는 중입니다...")
            
            with open(save_path, 'wb') as f:
                rubymarshal.writer.write(f, self.current_data)
                
            self.status_label.config(text=f"저장 성공: {save_path.split('/')[-1]}", fg="green")
            print("✅ 저장이 성공적으로 완료되었습니다!")
            messagebox.showinfo("저장 완료", "파일이 성공적으로 저장되었습니다!\n게임에서 정상적으로 로드되는지 확인해 보세요.")
            
        except Exception as e:
            error_msg = traceback.format_exc()
            print("\n🚨 파일을 저장하는 중 오류가 발생했습니다:\n" + error_msg)
            self.auto_copy_error(error_msg)
            messagebox.showerror("저장 오류", f"파일을 저장하는 중 오류가 발생했습니다.\n에러 로그가 클립보드에 복사되었습니다.\n\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = SaveEditorApp(root)
    root.mainloop()