"""M1 human menu-tuning runner for Exp1 v2.

The timer is active only while the operator reads feedback and chooses the next
menu decision. Numerical calibration/evaluation waits are recorded as wall time
but excluded from human active time.
"""

from __future__ import annotations

import argparse
import logging
import time

from common import (
    BUDGET_LEVELS,
    MAX_TRIALS,
    OBJECTIVES,
    RANGE_POLICIES,
    MenuDecision,
    append_jsonl,
    best_record,
    ensure_dirs,
    flatten_metric,
    get_basin_attrs,
    iter_tasks,
    load_base_config,
    method_dir,
    read_jsonl,
    run_trial,
    write_json,
)

LOGGER = logging.getLogger(__name__)


_LABEL_CN = {
    "objective": "优化目标 (objective)",
    "budget_level": "搜索预算 (budget_level)",
    "range_policy": "参数范围策略 (range_policy)",
}


def _prompt_choice(label: str, options: list[str], default: str) -> str:
    cn_label = _LABEL_CN.get(label, label)
    print(f"\n{cn_label}:")
    for idx, option in enumerate(options, 1):
        suffix = "  <- 默认 (回车选此)" if option == default else ""
        print(f"  [{idx}] {option}{suffix}")
    raw = input(f"请选择 {cn_label}(输入序号或直接回车用默认 {default}): ").strip()
    if not raw:
        return default
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    return raw


def _show_feedback(task: dict, history: list[dict], attrs: dict) -> None:
    print("\n" + "=" * 78)
    print(f"任务: {task['task_id']}   流域={task['basin_id']}   模型={task['model'].upper()}")
    print(f"气候标签: {task['climate_zone']}")
    if attrs:
        keys = ["aridity", "runoff_ratio", "baseflow_index", "frac_snow", "climate_zone"]
        readable = {k: attrs.get(k) for k in keys if attrs.get(k) is not None}
        if readable:
            print(f"流域属性: {readable}")
    if not history:
        print(f"本任务尚无历史 trial(将是第 1 次率定)。")
        return
    last = history[-1]
    print(f"\n上一 trial #{last['trial_idx']} 决策: {last.get('decision')}")
    print(
        "上一 trial 指标: "
        f"训练 NSE={flatten_metric(last, 'train', 'NSE')}  "
        f"测试 NSE={flatten_metric(last, 'test', 'NSE')}  "
        f"训练 KGE={flatten_metric(last, 'train', 'KGE')}  "
        f"测试 KGE={flatten_metric(last, 'test', 'KGE')}"
    )
    bh = last.get("boundary_hits", [])
    print(f"上一 trial 边界撞击 (boundary hits): {bh if bh else '无'}")
    best = best_record(history)
    if best:
        print(f"目前最佳: trial #{best['trial_idx']}  测试 NSE={flatten_metric(best, 'test', 'NSE')}")
    print(f"已用 trial 数: {len(history)} / {MAX_TRIALS}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run only one basin-model task")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing human trial log")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ensure_dirs()
    cfg = load_base_config()
    out_dir = method_dir("human_script")
    trial_log = out_dir / "trials.jsonl"
    if args.overwrite and trial_log.exists():
        trial_log.unlink()

    all_records = read_jsonl(trial_log)
    new_records = []

    for task in iter_tasks(smoke=args.smoke):
        task_history = [r for r in all_records if r.get("task_id") == task["task_id"]]
        attrs = get_basin_attrs(task["basin_id"], cfg)
        for trial_idx in range(len(task_history) + 1, MAX_TRIALS + 1):
            _show_feedback(task, task_history, attrs)
            print(f"\n>>> 开始第 {trial_idx} 次 trial 的决策(计时开始,仅从此刻到完成菜单选择/笔记计入 active 时间)")
            t_active = time.time()
            objective = _prompt_choice("objective", OBJECTIVES, "NSE")
            budget = _prompt_choice("budget_level", BUDGET_LEVELS, "default")
            policy_default = "boundary_expand" if task_history and task_history[-1].get("boundary_hits") else "default"
            range_policy = _prompt_choice("range_policy", RANGE_POLICIES, policy_default)

            # Freeform-mode extras: prompt for the 5 SCE-UA numeric hyperparams.
            # In preset mode these stay None and budget_level's preset is used.
            import os as _os
            from common import FREEFORM_BOUNDS
            rep = ngs = kstop = peps = pcento = None
            if _os.environ.get("EXP1_MODE", "preset").lower() == "freeform":
                bounds = FREEFORM_BOUNDS.get(task["model"], FREEFORM_BOUNDS["gr4j"])
                print("\nMode B 算法超参数(直接回车跳过 -> 用 budget_level 预设值;越界将自动 clamp):")
                def _num(label, lo, hi, cast, hint):
                    raw = input(f"  {label} [{lo}-{hi}, {hint}]: ").strip()
                    if not raw:
                        return None
                    try:
                        return cast(raw)
                    except ValueError:
                        return None
                rep    = _num("rep",    *bounds["rep"],    int,   hint="最大评估次数")
                ngs    = _num("ngs",    *bounds["ngs"],    int,   hint="并行复合体数,要求 rep>=5*ngs")
                kstop  = _num("kstop",  *bounds["kstop"],  int,   hint="收敛耐心代数")
                peps   = _num("peps",   *bounds["peps"],   float, hint="参数收敛阈值,越小越严格")
                pcento = _num("pcento", *bounds["pcento"], float, hint="目标函数%变化阈值,越小越严格")

            stop_raw = input("\n本次 trial 后是否停止该流域?(y=停止 / Enter 或 n=继续下一 trial): ").strip().lower()
            notes = input("简短诊断笔记(可空,Enter 跳过): ").strip()
            active_seconds = time.time() - t_active

            decision = MenuDecision(
                objective=objective,
                budget_level=budget,
                range_policy=range_policy,
                stop=stop_raw in ("y", "yes"),
                notes=notes,
                rep=rep, ngs=ngs, kstop=kstop, peps=peps, pcento=pcento,
            )
            previous_best = best_record(task_history)
            record = run_trial(
                method="M1",
                task=task,
                trial_idx=trial_idx,
                decision=decision,
                cfg=cfg,
                run_dir=out_dir,
                active_seconds=active_seconds,
                previous_best=previous_best,
            )
            append_jsonl(trial_log, record)
            all_records.append(record)
            task_history.append(record)
            new_records.append(record)
            print(f"\n>>> 第 {trial_idx} 次 trial 完成。本次 active={active_seconds:.1f}s, 总 wall={record['wall_time_s']:.1f}s")
            print(f"    测试 NSE={flatten_metric(record, 'test', 'NSE')}  测试 KGE={flatten_metric(record, 'test', 'KGE')}")
            if decision.stop:
                print(f"    选择 stop=y,跳到下一个流域。")
                break

    write_json(out_dir / "summary.json", {"method": "M1", "new_records": len(new_records)})
    print(f"\n本次 session 共新增 {len(new_records)} 条 M1 trial 记录 -> {trial_log}")


if __name__ == "__main__":
    main()
