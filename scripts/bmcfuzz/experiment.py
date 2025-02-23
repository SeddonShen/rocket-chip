import os
import re
import sys
import argparse
import subprocess
import time

from runtools import log_init, clear_logs, log_message, reset_terminal
from runtools import FuzzArgs, NOOP_HOME
from runtools import kill_process_and_children

def run_and_capture_output(cmd, timeout):
    start_time = time.time()
    pre_time = 0
    time_interval = 20
    log_message(cmd)
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, shell=True)

    coverage_lines = []

    try:
        for line in iter(process.stdout.readline, ""):
            elapsed_time = time.time() - start_time
            
            if "Total Coverage" in line and elapsed_time - pre_time > time_interval:
                pre_time = elapsed_time
                hours = int(elapsed_time / 3600)
                minutes = int((elapsed_time % 3600) / 60)
                seconds = int(elapsed_time % 60)
                line = "Coverage:"+line.split(' ')[-1].replace('\n','')
                cover_message = f"{hours:>3}h{minutes:>3}m{seconds:>3}s {line}"
                log_message(cover_message, print_message=False)
                coverage_lines.append(cover_message)
            
            if elapsed_time > timeout:
                log_message("Process timeout, terminating")
                kill_process_and_children(process.pid)
                break
        
        process.wait()
    except KeyboardInterrupt:
        log_message("Process interrupted, terminating")
        kill_process_and_children(process.pid)
    except Exception as e:
        log_message(f"Error: {e}")
        kill_process_and_children(process.pid)
    finally:
        log_message("Closing process")
        process.stdout.close()
        process.stderr.close()
        reset_terminal()
    
    return coverage_lines

def fuzz_init(args):
    fuzzer = FuzzArgs()
    fuzzer.cover_type = args.cover_type
    fuzzer.make_log_file = os.path.join(NOOP_HOME, "tmp", "make_fuzzer.log")
    fuzzer.make_fuzzer()

def do_fuzz(args):
    if args.do_xfuzz:
        fuzz_name = "xfuzz"
    elif args.do_pathfuzz:
        fuzz_name = "pathfuzz"
    log_init(name=fuzz_name)
    log_message(f"Running {fuzz_name}")
    log_message("clearing coverage points")
    cover_points_file = os.path.join(NOOP_HOME, "ccover", "Formal", "coverTasks", "cover_points.csv")
    if os.path.exists(cover_points_file):
        os.remove(cover_points_file)
    
    fuzzer = FuzzArgs()

    fuzzer.cover_type = args.cover_type
    # fuzzer.max_runs = 1000000
    if args.do_xfuzz:
        fuzzer.corpus_input = os.path.join(NOOP_HOME, "corpus", "linearized", "riscv-dv")
    elif args.do_pathfuzz:
        fuzzer.corpus_input = os.path.join(NOOP_HOME, "corpus", "footprints", "riscv-dv")

    fuzzer.continue_on_errors = True
    fuzzer.only_fuzz = True
    
    fuzzer.max_instr = 10000
    fuzzer.max_cycle = 10000

    fuzzer.as_footprint = args.do_pathfuzz

    fuzz_cmd = fuzzer.generate_fuzz_command()

    coverage_lines = run_and_capture_output(fuzz_cmd, args.timeout)
    log_message("Fuzzing done")

    log_message("Output coverage")
    output_file = os.path.join(NOOP_HOME, "tmp", "exp", f"{fuzz_name}.log")
    with open(output_file, "w") as f:
        f.write("\n".join(coverage_lines))

def do_bmc(args):
    fuzz_cmd = f"cd {NOOP_HOME} && source env.sh"
    if args.do_hypfuzz:
        fuzz_name = "hypfuzz"
        fuzz_cmd += f" && python3 {NOOP_HOME}/ccover/Formal/Scheduler.py -c {args.cover_type}"
    elif args.do_bmcfuzz:
        fuzz_name = "bmcfuzz"
        fuzz_cmd += f" && python3 {NOOP_HOME}/ccover/BMCFuzz.py -f -d -c {args.cover_type}"
    fuzz_cmd = f"bash -c \'{fuzz_cmd}\'"
    log_init(name=fuzz_name)
    log_message(f"Running {fuzz_name}")

    coverage_lines = run_and_capture_output(fuzz_cmd, args.timeout)
    log_message("Fuzzing done")

    log_message("Output coverage")
    output_file = os.path.join(NOOP_HOME, "tmp", "exp", f"{fuzz_name}.log")
    with open(output_file, "w") as f:
        f.write("\n".join(coverage_lines))

if __name__ == "__main__":
    os.chdir(NOOP_HOME)
    # clear_logs()
    log_init()
    
    parser = argparse.ArgumentParser()

    default_cover_type = "toggle"
    default_timeout = 30 * 60 * 60
    # default_timeout = 72 * 60 * 60
    # default_timeout = 60

    parser.add_argument("--cover-type", "-c", type=str, default=default_cover_type, help="Coverage type")
    parser.add_argument("--timeout", "-t", type=int, default=default_timeout, help="Timeout")
    parser.add_argument("--init", "-i", action='store_true', help="Initialize fuzzing")

    parser.add_argument("--do-xfuzz", "-dx", action='store_true', help="Do xfuzz")
    parser.add_argument("--do-pathfuzz", "-dp", action='store_true', help="Do pathfuzz")

    parser.add_argument("--do-hypfuzz", "-dh", action='store_true', help="Do hypfuzz")
    parser.add_argument("--do-bmcfuzz", "-db", action='store_true', help="Do bmcfuzz")

    args = parser.parse_args()

    if args.init:
        fuzz_init(args)
    
    if args.do_xfuzz or args.do_pathfuzz:
        do_fuzz(args)

    if args.do_hypfuzz or args.do_bmcfuzz:
        do_bmc(args)
    
