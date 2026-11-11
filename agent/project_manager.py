"""Local Projects & Nutrition Manager for SmartGlass Agent on Windows (D: drive).

Gives the voice+vision agent workspace/project awareness (like Claude Projects / Harmony)
and dedicated nutrition/calorie tracking stored directly in d:\\agents\\smartglass\\projects.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("visionclaw-projects")

PROJECTS_ROOT = Path(os.environ.get("SMARTGLASS_PROJECTS_DIR", r"d:\agents\smartglass\projects"))
STATE_FILE = PROJECTS_ROOT / "active_state.json"

PROJECT_ALIASES = {
    "питание": "nutrition",
    "калории": "nutrition",
    "рацион": "nutrition",
    "здоровье": "nutrition",
    "еда": "nutrition",
    "nutrition": "nutrition",
    "ассистент": "assistant",
    "заметки": "assistant",
    "задачи": "assistant",
    "assistant": "assistant",
    "работа": "work",
    "проекты": "work",
    "work": "work",
    "перевод": "translator",
    "переводчик": "translator",
    "языки": "translator",
    "английский": "translator",
    "казахский": "translator",
    "translator": "translator",
}


def ensure_projects_root() -> Path:
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    return PROJECTS_ROOT


def resolve_project_name(name: str) -> str:
    clean = name.strip().lower()
    if clean in PROJECT_ALIASES:
        return PROJECT_ALIASES[clean]
    for alias, target in PROJECT_ALIASES.items():
        if alias in clean:
            return target
    # Sanitize custom folder name
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in clean).strip("_")
    return safe or "assistant"


def get_active_project() -> str:
    ensure_projects_root()
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return data.get("active_project", "nutrition")
        except Exception:
            pass
    return "nutrition"


def set_active_project(project_name: str) -> str:
    ensure_projects_root()
    resolved = resolve_project_name(project_name)
    proj_dir = PROJECTS_ROOT / resolved
    proj_dir.mkdir(parents=True, exist_ok=True)
    ctx_file = proj_dir / "context.md"
    if not ctx_file.exists():
        ctx_file.write_text(f"# Проект: {project_name}\n\nМатериалы и заметки проекта.\n", encoding="utf-8")
    STATE_FILE.write_text(
        json.dumps({"active_project": resolved, "updated_at": datetime.now().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return resolved


def list_all_projects() -> list[dict[str, str]]:
    ensure_projects_root()
    active = get_active_project()
    result = []
    for item in sorted(PROJECTS_ROOT.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            files = [f.name for f in item.iterdir() if f.is_file()]
            title = item.name
            ctx_path = item / "context.md"
            if ctx_path.exists():
                first_line = ctx_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                if first_line:
                    title = first_line[0].lstrip("# ").strip()
            result.append({
                "id": item.name,
                "title": title,
                "active": "YES" if item.name == active else "NO",
                "files": ", ".join(files[:10]),
            })
    return result


def _read_single_file(file_path: Path, max_chars: int = 6000) -> str:
    suffix = file_path.suffix.lower()
    try:
        if suffix in (".md", ".txt", ".json", ".csv", ".py", ".yaml", ".yml"):
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            return text[:max_chars]
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(file_path))
                pages = [page.extract_text() or "" for page in reader.pages[:10]]
                return "\n".join(pages)[:max_chars]
            except Exception as e:
                return f"[Ошибка чтения PDF {file_path.name}: {e}]"
    except Exception as e:
        return f"[Ошибка чтения файла {file_path.name}: {e}]"
    return ""


def read_project_materials(project_name: str | None = None, query: str | None = None) -> str:
    ensure_projects_root()
    resolved = resolve_project_name(project_name) if project_name else get_active_project()
    proj_dir = PROJECTS_ROOT / resolved
    if not proj_dir.exists():
        return f"Проект '{resolved}' пока не существует. Доступные проекты: {[p['id'] for p in list_all_projects()]}"

    sections: list[str] = [f"=== АКТИВНЫЙ ПРОЕКТ: {resolved} (Папка: {proj_dir}) ==="]
    for f in sorted(proj_dir.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        content = _read_single_file(f)
        if not content:
            continue
        if query:
            q_low = query.lower()
            if q_low not in content.lower() and q_low not in f.name.lower() and f.name != "context.md":
                continue
        sections.append(f"\n--- Файл: {f.name} ---\n{content}")

    return "\n".join(sections)


def save_material_to_project(filename: str, content: str, project_name: str | None = None, append: bool = True) -> str:
    ensure_projects_root()
    resolved = resolve_project_name(project_name) if project_name else get_active_project()
    proj_dir = PROJECTS_ROOT / resolved
    proj_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename).name
    if not any(safe_name.endswith(ext) for ext in (".md", ".txt", ".json", ".csv")):
        safe_name += ".md"
    target = proj_dir / safe_name

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if append and target.exists():
        existing = target.read_text(encoding="utf-8", errors="ignore")
        new_text = f"{existing.rstrip()}\n\n### Запись [{timestamp}]\n{content}\n"
    else:
        new_text = f"### Запись [{timestamp}]\n{content}\n" if append else content

    target.write_text(new_text, encoding="utf-8")
    return f"Сохранено в проект '{resolved}', файл '{safe_name}'."


def log_meal_entry(
    meal_name: str,
    calories: int,
    protein_g: float = 0,
    fat_g: float = 0,
    carbs_g: float = 0,
    weight_g: float = 0,
    notes: str = "",
) -> dict:
    """Logs a meal into nutrition/food_log.json and updates nutrition/food_diary.md."""
    ensure_projects_root()
    nut_dir = PROJECTS_ROOT / "nutrition"
    nut_dir.mkdir(parents=True, exist_ok=True)
    log_file = nut_dir / "food_log.json"
    diary_file = nut_dir / "food_diary.md"

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    entries = []
    if log_file.exists():
        try:
            entries = json.loads(log_file.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    entry = {
        "date": today_str,
        "time": time_str,
        "meal": meal_name,
        "weight_g": weight_g,
        "calories": calories,
        "protein_g": protein_g,
        "fat_g": fat_g,
        "carbs_g": carbs_g,
        "notes": notes,
    }
    entries.append(entry)
    log_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    # Calculate today's totals
    today_entries = [e for e in entries if e.get("date") == today_str]
    total_cal = sum(int(e.get("calories", 0)) for e in today_entries)
    total_p = sum(float(e.get("protein_g", 0)) for e in today_entries)
    total_f = sum(float(e.get("fat_g", 0)) for e in today_entries)
    total_c = sum(float(e.get("carbs_g", 0)) for e in today_entries)

    daily_goal = 2100
    remaining_cal = daily_goal - total_cal

    # Update readable markdown diary
    md_lines = [
        "# Дневник питания (Food Diary)\n",
        f"## Итоги за сегодня ({today_str}):",
        f"- **Съедено калорий:** {total_cal} / {daily_goal} ккал (Осталось: {remaining_cal} ккал)",
        f"- **Белки:** {total_p:.1f} г | **Жиры:** {total_f:.1f} г | **Углеводы:** {total_c:.1f} г\n",
        "### Приёмы пищи за сегодня:",
    ]
    for e in today_entries:
        w_info = f" (~{int(e['weight_g'])}г)" if e.get("weight_g") else ""
        md_lines.append(
            f"- **[{e['time']}] {e['meal']}{w_info}** — {e['calories']} ккал "
            f"(Б: {e['protein_g']}г, Ж: {e['fat_g']}г, У: {e['carbs_g']}г) {e.get('notes', '')}"
        )
    diary_file.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return {
        "logged": entry,
        "today_total_calories": total_cal,
        "daily_goal_calories": daily_goal,
        "remaining_calories": remaining_cal,
        "today_protein_g": round(total_p, 1),
        "today_fat_g": round(total_f, 1),
        "today_carbs_g": round(total_c, 1),
        "meals_count_today": len(today_entries),
    }


def get_today_nutrition_summary() -> dict:
    ensure_projects_root()
    nut_dir = PROJECTS_ROOT / "nutrition"
    log_file = nut_dir / "food_log.json"
    today_str = datetime.now().strftime("%Y-%m-%d")
    entries = []
    if log_file.exists():
        try:
            entries = json.loads(log_file.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    today_entries = [e for e in entries if e.get("date") == today_str]
    total_cal = sum(int(e.get("calories", 0)) for e in today_entries)
    total_p = sum(float(e.get("protein_g", 0)) for e in today_entries)
    total_f = sum(float(e.get("fat_g", 0)) for e in today_entries)
    total_c = sum(float(e.get("carbs_g", 0)) for e in today_entries)
    daily_goal = 2100
    return {
        "date": today_str,
        "today_total_calories": total_cal,
        "daily_goal_calories": daily_goal,
        "remaining_calories": daily_goal - total_cal,
        "today_protein_g": round(total_p, 1),
        "today_fat_g": round(total_f, 1),
        "today_carbs_g": round(total_c, 1),
        "meals": today_entries,
    }

