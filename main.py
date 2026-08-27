import os
import json

def load_data():
    if os.path.exists("bot_data.json"):
        with open("bot_data.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "menu": {
            "root": {
                "name": "القائمة الرئيسية",
                "submenus": {},
                "files": []
            }
        }
    }

def save_data(data):
    with open("bot_data.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_node(data, path):
    curr = data["menu"]["root"]
    for p in path:
        if "submenus" in curr and p in curr["submenus"]:
            curr = curr["submenus"][p]
        else:
            return None
    return curr

def is_admin(user_id):
    return user_id == 5734654153

def show_main_menu(user_id):
    if is_admin(user_id):
        return "أهلاً بك، أنت مسؤول. يمكنك تعديل القوائم."
    else:
        return "أهلاً بك، اختر إحدى المراحل."

def show_stage(stage_name, user_id):
    if is_admin(user_id):
        return f"مرحلة {stage_name}: يمكنك تعديل المواد."
    else:
        return f"مرحلة {stage_name}: اختر المادة لمشاهدة المحاضرات."
