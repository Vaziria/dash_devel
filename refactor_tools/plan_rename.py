from io import TextIOWrapper
import os
from pydantic import BaseModel
from typing import List, Generator
import re
import shutil

APPLY=True


RENAME_TYPE = "rename"
REPLACE_TYPE = "replace"

BASE_PLAN = "./refactor_plan_data"

def fname_base(*args):
    return os.path.join(BASE_PLAN, *args)


    
    

class PlanReplaceItem(BaseModel):
    sample: str
    text: str
    replace_to: str
    start: int
    
    def replace(self, content: str) -> str:
        newcontent = content[:self.start] + self.replace_to + content[self.start+len(self.text):]
        return newcontent
    
    def to_md(self, ident=0) -> str:
        tabs = "\t" * ident
        sample = self.sample.replace("\n", f"\n{tabs}")
        replace_sample = sample.replace(self.text, self.replace_to)
        content = f"{tabs}- **{self.text}** replaced to **{self.replace_to}**: \n{tabs}```\n{tabs}{sample}\n{tabs}```\n"
        content += f"{tabs}jadi:\n"
        content += f"{tabs}```\n{tabs}{replace_sample}\n{tabs}```\n"
        
        return content
    
        
class PlanPath(BaseModel):
    is_file: bool
    path: str

class PlanItem(BaseModel):
    plan_type: str
    path: PlanPath
    is_ignored: bool
    newpath: str
    replaces: List[PlanReplaceItem]
    
    def to_md(self, ident=0) -> str:
        tabs = "\t" * ident
        
        tipe = "file"
        if not self.path.is_file:
            tipe = "directory"
        
        newpath = ""
        if self.newpath:
            newpath = f"rename to **{self.newpath}**"
        content = f"{tabs}- {tipe} **{self.path.path}** {newpath}\n" 
        
        for repl in self.replaces:
            content += repl.to_md(ident=ident+1)+"\n"

        
        return content
    
    
class PlanTextReplacer(BaseModel):
    texts: List[List[str]]
    skip_ext: List[str]
    skip_texts: List[str]
    
    
    def find_text(self, plan: PlanItem) -> bool:
        found = False
        
        for ext in self.skip_ext:
           if plan.path.path.endswith(ext):
               return found
        
        # print(plan.path.path)
        with open(plan.path.path, 'r') as out:
            content = out.read()
            for text in self.texts:
                
                while True:
                    cocok = re.search(f"({text[0]})", content)
                    if cocok == None:
                        break
                    
                    groups = cocok.groups()
                    if len(groups) == 0:
                        break
                    
                    
                    
                    sample = 8
                    start = cocok.start() - sample
                    
                    
                    if start < 0:
                        start = 0
                    
                    samplestr = content[start:cocok.start() + len(text[0]) + sample]
                    samplestr = samplestr.replace("\n", "\\n")
                    
                    # check skip text
                    skip = False
                    for sktext in self.skip_texts:
                        if samplestr.find(sktext) != -1:
                            skip = True
                            break
                        
                    if skip:
                        break
                    
                    found = True
                    rep_item = PlanReplaceItem(sample=samplestr, start=cocok.start(), replace_to=text[1],text=text[0])
                    content = rep_item.replace(content)
                    plan.replaces.append(rep_item)
                    
        if found and APPLY:
            with open(plan.path.path, 'w+') as out:
                out.write(content)

        return found


def memoize(funcdata):
    data = {}
    def memofunc(path: str):
        if data.get(path, False) == False:
            hasil = funcdata(path)
            data[path] = True
            return hasil
        
        return None
        
    return memofunc

@memoize
def makedatadir(path: str):
    if os.path.exists(path):
        return
    return os.makedirs(path)

class Remover(BaseModel):
    backup_remover: str
    data: List[str]
    
    def check(self, path: str) -> bool:
        
        for prefix in self.data:
            if path.startswith(prefix):
                
                if APPLY:
                    path = path.lstrip("./")
                    newpath = fname_base(self.backup_remover, path)
                    dirname = os.path.dirname(newpath)
                    print("deleting", path)
                    makedatadir(dirname)
                    os.rename(path, newpath)
                    
                    
                return True
        
        return False

class PlanCreator(BaseModel):
    ignores: List[str]
    path_replace: List[List[str]]
    base: str
    plan_replacer: PlanTextReplacer
    hidden_directories: List[str]
    remover: Remover
    
    
        
    def check_rename(self, item: PlanItem) -> bool:
        
        found = False
            
        for rep in self.path_replace:
            if item.path.path.find(rep[0]) != -1:
                item.is_ignored = False
                item.newpath = item.path.path.replace(rep[0], rep[1])
                found = True
                break
            
        if found and APPLY:
            shutil.move(item.path.path, item.newpath)
            
        return found
    
    def check_ignores(self, path: str):
        for c in self.ignores:
            if path.startswith(c):
                return True
        
        return False
    
    def iterate_path(self) -> Generator[int, None, None]:
        
        base_pool = []
        base_pool.extend(self.hidden_directories)
        base_pool.append(self.base)
        
        for base in base_pool:
            for root, dirs, files in os.walk(base):
                
                for dirt in dirs:
                    dirt = os.path.join(root, dirt)
                    
                    if self.check_ignores(dirt):
                        continue
                        
                    
                    yield PlanPath(
                        is_file=False,
                        path=dirt
                    )
                    
                
                for file in files:
                    
                    file = os.path.join(root, file)
                    
                    if self.remover.check(file):
                        continue
                    
                    if self.check_ignores(file):
                        continue
                    
                    yield PlanPath(
                        is_file=True,
                        path=file
                    )
            
        
                
                
            
            
    
    def iterate(self):
        

        for path in self.iterate_path():
            item = PlanItem(
                plan_type=RENAME_TYPE,
                path=path, 
                is_ignored=True, 
                newpath="", 
                replaces=[]
            )
            
            
            if item.path.is_file:
                if self.plan_replacer.find_text(item):
                    yield item
                    
            self.check_rename(item)
            
            if not item.is_ignored:
                yield item
  


class PlanWritter:
    writer: TextIOWrapper
    
    def __init__(self, writer: TextIOWrapper) -> None:
        self.writer = writer

    def write_plan(self, plan: PlanItem):
        line = plan.model_dump_json() + "\n"
        self.writer.write(line)
        

KB_SIZE = 1000
MB_SIZE = 1000000 
        

class MdWriter:
    limit: int
    size: int
    active_file: str
    file: TextIOWrapper
    
    def __init__(self, limit: int) -> None:
        self.file = None
        self.size = 0
        self.limit = limit
        
        prevbase = fname_base("preview")
        
        if os.path.exists(prevbase):
            shutil.rmtree(prevbase)
        
        os.mkdir(prevbase)
    
    def get_writer(self, fname: str) -> TextIOWrapper:
        if self.file == None:
            self.active_file = fname
            self.file = open(fname, "w+")
            self.file.write("## Review Refactor\n\n")
            
            return self.file
        
        if self.active_file != fname:
            self.active_file = fname
            self.file.close()
            self.file = open(fname, "w+")
            self.file.write("## Review Refactor\n\n")
            
           
        return self.file
    
    def write(self, text: str):
        ind = int(self.size / self.limit)
        
        fname = fname_base("preview", f"preview_{ind}.md")
        writer = self.get_writer(fname)
        
        self.size += writer.write(text)
        
        
        
    
    


def main():
    replace_path = [
        ["dash","unfy"],   
    ]
    
    textreplace = [
        ["security@dash.org", "unifyroomcoin@gmail.com"],
        ["https://github.com/dashpay/dash", "https://github.com/unifyroom/unifycoin"],
        ["Dash whitepaper", "Unifyroom whitepaper"],
        ["Dash Core", "Unifyroom Core"],
        ["dash core", "unifyroom core"],
        ["Dash node", "Unifyroom node"],
        ["Dash Node", "Unifyroom Node"],
        ["staydashy.com", "https://discord.gg/gsMznV3q"],
        ["dash.org/forum", "https://discord.gg/gsMznV3q"],
        ["https://www.dash.org/downloads/", "https://github.com/unifyroom/unifycoin/releases"],
        ["https://gitlab.com/dashpay/dash", "https://github.com/unifyroom/unifycoin"],
        ["www.dash.org", "unifyroom.com"],
        ["dash.org", "unifyroom.com"],
        ["dashpay/dashd", "unifyroom/unifycoin"],
        ["dashpay", "unifyroom"],
        ["Dashpay", "Unifyroom"],
        ["DASH", "UNFY"],
        ["dash", "unfy"],
        ["Dash", "Unifyroom"],
        ["DashCrashInfo", "UnfyCrashInfo"],
        ["Dash", "Unfy"],              
    ]

    ignores = [
        "./.git/",
        "./.vscode",
        "./depends/x86_64-pc-linux-gnu/",
        "./depends/x86_64-w64-mingw32/",
        "./depends/sources/",
        "./refactor_tools",
        "./refactor_plan_data",
        "./src/univalue/test",
        "./src/immer/test/oss-fuzz/data",
        "./src/llmq/.deps",
        "./refactor_plan_data",
        "./workspace/refactor_plan_data"
    ]
    
    dir_stucture = [
        "",
        "asset_review",
        
    ]
    
    size_preview = 200 *KB_SIZE
    
    for dirstruc in dir_stucture:
        if not os.path.exists(fname_base(dirstruc)):
            os.makedirs(fname_base(dirstruc))
        
    plan_filepath = fname_base("plan_refactor.jsonlist")
    
    plan = PlanCreator(
        ignores=ignores, 
        path_replace=replace_path, 
        base="./",
        plan_replacer=PlanTextReplacer(
            texts=textreplace,
            skip_ext=[
                ".tar.gz",
                ".zip",
                ".bmp",
                ".dat",
                ".jpg",
                ".png",
                ".o",
                ".a",
                
                "omine",
                ".exe",
                "src/dashd",
                "src/dash-cli",
                "src/dash-tx",
                "src/qt/dash-qt",
                "src/dash-wallet",
                "test/test_dash-qt",
                "/dashbls/runbench",
                "/dashbls/runtest",
                "/bench/bench_dash",
                "/test/object",
                "/test/test_dash",
                "/test/fuzz/fuzz",
                
                ".dll",
                ".lib",
                "secp256k1/gen_context",
                ".qm",
                ".icns",
                ".ico",
                ".otf",
                ".raw",
                ".so.0.0.0",
                ".so",
                ".so.0",
                ".tiff",
            ],
            skip_texts=[
                "lodash",
                "Lodash"
            ]
        ),
        hidden_directories=[
            "./.github/"
        ],
        remover=Remover(
            backup_remover="backup_delete",
            data=[
                "./doc/release-notes/dash/"
            ]
        )
    )
    
    with open(plan_filepath, "w+") as out:
        writer = PlanWritter(out)
        
        mdwriter = MdWriter(size_preview)
    
        for item in plan.iterate():
            writer.write_plan(item)
            mdwriter.write(item.to_md())
            
            print("planning", item.path.path)
                
    print(f"plan saved on {plan_filepath}")
    
    # if APPLY:
    #     shutil.rmtree(BASE_PLAN)
    

if __name__ == "__main__":
    main()