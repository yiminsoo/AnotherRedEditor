import sys
import traceback
import codecs
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import rubymarshal.reader
import rubymarshal.classes

# =========================================================
# 1. rubymarshal 라이브러리 버그 패치 (링크 우회)
# =========================================================
original_read = rubymarshal.reader.Reader.read

def patched_read(self, *args, **kwargs):
    try:
        return original_read(self, *args, **kwargs)
    except ValueError as e:
        if "invalid link destination" in str(e):
            return f"<Link Error Bypassed>"
        raise

rubymarshal.reader.Reader.read = patched_read

# =========================================================
# 2. rubymarshal 라이브러리 버그 패치 (인코딩 우회)
# =========================================================
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


# =========================================================
# 3. GUI 뷰어 클래스 정의
# =========================================================
class SaveViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("포켓몬 세이브 데이터 뷰어")
        self.root.geometry("1100x700")

        # --- 상단 컨트롤 패널 (버튼 영역) ---
        top_frame = tk.Frame(self.root, pady=10, padx=10)
        top_frame.pack(side="top", fill="x")

        self.load_btn = tk.Button(
            top_frame, 
            text="📁 세이브 파일 불러오기 (.rxdata)", 
            font=("맑은 고딕", 10, "bold"),
            command=self.load_file
        )
        self.load_btn.pack(side="left")
        
        self.status_label = tk.Label(top_frame, text="파일을 불러와주세요.", fg="gray")
        self.status_label.pack(side="left", padx=15)

        # --- 메인 트리뷰(Treeview) 영역 ---
        columns = ("Type", "Value", "Path")
        self.tree = ttk.Treeview(self.root, columns=columns)
        
        self.tree.heading("#0", text="이름 (Name / Key)")
        self.tree.heading("Type", text="데이터 타입 (Type)")
        self.tree.heading("Value", text="값 (Value)")
        self.tree.heading("Path", text="경로 (Path)")
        
        self.tree.column("#0", width=250, anchor='w')
        self.tree.column("Type", width=150, anchor='w')
        self.tree.column("Value", width=250, anchor='w')
        self.tree.column("Path", width=400, anchor='w')

        # 스크롤바 추가
        vsb = ttk.Scrollbar(self.root, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self.root, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.tree.pack(side='left', fill='both', expand=True)

    # --- 파일 불러오기 기능 ---
    def load_file(self):
        # 파일 탐색기 열기
        file_path = filedialog.askopenfilename(
            title="세이브 파일 선택",
            filetypes=[("RPG Maker Save", "*.rxdata"), ("All Files", "*.*")]
        )
        
        if not file_path:
            return # 취소 버튼을 누른 경우 종료

        # 기존에 열려있던 데이터가 있다면 화면에서 모두 지우기
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.root.title(f"포켓몬 세이브 데이터 뷰어 - {file_path}")
        self.status_label.config(text="데이터를 읽고 렌더링하는 중입니다...", fg="blue")
        self.root.update() # 화면 상태 즉시 반영

        try:
            with open(file_path, 'rb') as f:
                print(f"\n[{file_path}] 파일 로딩 중...")
                content = rubymarshal.reader.load(f)
                
                # 트리뷰에 데이터 그리기 시작
                self.insert_node("", content, name="SaveData", path="root0")
                
                print("✅ 렌더링 완료!")
                self.status_label.config(text=f"로드 완료: {file_path.split('/')[-1]}", fg="green")
                
        except Exception as e:
            error_msg = traceback.format_exc()
            print("파일을 읽는 도중 오류가 발생했습니다:\n")
            print(error_msg)
            messagebox.showerror("오류 발생", f"파일을 읽는 데 실패했습니다.\n\n{e}")
            self.status_label.config(text="파일 로드 실패", fg="red")

    # --- 데이터 트리 삽입 로직 ---
    def insert_node(self, parent_id, data, name="root", path="root"):
        dtype = type(data).__name__
        value_str = ""

        if isinstance(data, rubymarshal.classes.RubyObject):
            class_name = "UnknownClass"
            if hasattr(data, 'class_symbol'):
                class_name = str(getattr(data.class_symbol, 'name', data.class_symbol))
            elif hasattr(data, 'sym'):
                class_name = str(getattr(data.sym, 'name', data.sym))
            
            value_str = f"Ruby Object ({class_name})"
            node_id = self.tree.insert(parent_id, 'end', text=str(name), values=(dtype, value_str, path))
            
            if hasattr(data, 'attributes'):
                new_base_path = f"{path}@rb:attributes"
                for key, val in data.attributes.items():
                    key_name = str(getattr(key, 'name', key))
                    child_path = f"{new_base_path}{key_name}"
                    self.insert_node(node_id, val, name=key_name, path=child_path)

        elif isinstance(data, dict):
            value_str = f"Hash (크기: {len(data)})"
            node_id = self.tree.insert(parent_id, 'end', text=str(name), values=(dtype, value_str, path))
            for key, val in data.items():
                key_name = str(getattr(key, 'name', key))
                child_path = f"{path}{key_name}"
                self.insert_node(node_id, val, name=key_name, path=child_path)

        elif isinstance(data, list):
            value_str = f"Array (크기: {len(data)})"
            node_id = self.tree.insert(parent_id, 'end', text=str(name), values=(dtype, value_str, path))
            for i in range(len(data)):
                child_path = f"{path}{i}"
                self.insert_node(node_id, data[i], name=f"Index[{i}]", path=child_path)

        elif isinstance(data, rubymarshal.classes.Symbol):
            value_str = f":{data.name}"
            self.tree.insert(parent_id, 'end', text=str(name), values=("Symbol", value_str, path))

        else:
            if isinstance(data, bytes):
                try:
                    value_str = data.decode('utf-8')
                except UnicodeDecodeError:
                    value_str = f"<Binary Data: {len(data)} bytes>"
            else:
                value_str = str(data)
                
            if len(value_str) > 100:
                value_str = value_str[:97] + "..."
                
            self.tree.insert(parent_id, 'end', text=str(name), values=(dtype, value_str, path))


# =========================================================
# 4. 앱 실행
# =========================================================
if __name__ == "__main__":
    # 아무 파일도 로드하지 않은 상태로 빈 윈도우 먼저 띄우기
    root = tk.Tk()
    app = SaveViewerApp(root)
    root.mainloop()