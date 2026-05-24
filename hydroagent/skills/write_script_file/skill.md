---
name: Write Script File
description: Write a Python script to disk then run it
keywords: [script, write, run, python, file, execution]
tools: [write_script_file]
when_to_use: Use this skill when you need to generate a Python script dynamically (based on user input or derived logic) and immediately execute it, saving the script to disk for persistence or debugging.
---

## Write Script File 工作流

此技能用于将一段 Python 脚本代码写入磁盘文件，然后执行该脚本。它包装了 `open()`、`write()` 等内置函数以及 `subprocess` 或 `exec()` 运行机制，提供了安全的写入与执行控制。

### 使用时机
- 需要根据动态信息生成 Python 脚本并运行。
- 需要将脚本保留在磁盘以备后续检查或重用。
- 需要执行一段较长的、多行的 Python 代码，且不能通过单次 `exec` 完成（需要独立进程或环境隔离）。

### 工作流步骤

1. **接收脚本内容与路径**  
   用户提供脚本源代码（字符串）和保存路径（例如 `/tmp/script.py`）。可选的参数包括：是否覆盖已有文件、执行时的额外参数、执行超时时间等。

2. **验证脚本内容**  
   检查脚本是否包含可能破坏系统的危险操作（如 `os.system`, `__import__('os').system` 等恶意模式），并提示用户确认。若安全性要求高，可跳过此步并直接写入。

3. **写入文件**  
   使用 `open()` 以写入模式（`'w'`）打开目标路径，使用 `write()` 写入脚本内容，确保使用 `utf-8` 编码。写入后关闭文件。

   ```python
   with open(path, 'w', encoding='utf-8') as f:
       f.write(script_content)
   ```

4. **设置执行权限**（可选）  
   在 Unix 系统上，使用 `os.chmod(path, 0o755)` 添加可执行权限。

5. **执行脚本**  
   使用 `subprocess.run(['python', path], capture_output=True, text=True)` 启动子进程执行。也可以使用 `exec()` 在同一个进程中直接执行（需谨慎）。推荐子进程方式以隔离错误和副作用。

   ```python
   import subprocess
   result = subprocess.run(['python', path], capture_output=True, text=True, timeout=30)
   ```

6. **返回结果**  
   返回执行的标准输出（`result.stdout`）、标准错误（`result.stderr`）以及返回码（`result.returncode`）。如果超时或执行失败，抛出相应异常。

### 参数说明

| 参数名         | 类型     | 必需 | 默认值    | 说明                               |
|----------------|----------|------|-----------|------------------------------------|
| `script_content` | string | 是   | -         | 待写入的 Python 源代码              |
| `file_path`    | string   | 是   | -         | 保存脚本的完整路径（含文件名）       |
| `overwrite`    | bool     | 否   | `False`   | 是否覆盖已存在文件                  |
| `exec_mode`    | string   | 否   | `'subprocess'` | 执行方式，可选 `'subprocess'` 或 `'exec'` |
| `timeout`      | int      | 否   | `30`      | 子进程执行超时时间（秒）             |

### 注意事项
- 子进程执行方式更安全，避免当前进程被恶意代码影响。
- 写入路径应限制在安全目录（如 `/tmp` 或指定工作目录），防止覆盖系统文件。
- 若需传递参数给脚本，可在 `subprocess.run` 的 `args` 中添加额外项，或通过环境变量传递。
- 执行 `exec` 模式时，脚本的全局变量可能污染当前命名空间，建议在隔离的 `globals` 字典中执行。
- 此技能依赖于 Python 解释器存在于系统 PATH 中。