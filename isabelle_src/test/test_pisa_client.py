import os
import socket
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv

import pytest

load_dotenv()

PISA_JAR_PATH = os.environ.get(
    "PISA_JAR_PATH", "../target/scala-2.13/pisa-server-assembly-0.1.jar"
)
ISABELLE_PATH = os.environ.get("ISABELLE_PATH", "../Isabelle2024")
L4V_PATH = os.environ.get("L4V_PATH", "../L4V_FVEL/l4v")


def wait_for_port(port, host="127.0.0.1", timeout=30.0):
    start_time = time.perf_counter()
    while True:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return
        except OSError:
            time.sleep(0.5)
            if time.perf_counter() - start_time >= timeout:
                raise TimeoutError(
                    f"Port {port} on {host} not accepting connections after {timeout}s"
                )


def kill_port_process(port):
    os.system(f"lsof -ti:{port} | xargs kill -9 2>/dev/null || true")


class TestPisaEnv:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        self.port = 19999
        kill_port_process(self.port)
        yield
        kill_port_process(self.port)

    def test_pisa_env_init(self):
        from utils.pisa_client import PisaEnv

        theory_file = str(Path(__file__).parent / "assets/Test.thy")
        working_dir = str(Path(theory_file).parent)

        process = subprocess.Popen(
            ["java", "-jar", PISA_JAR_PATH, str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            wait_for_port(self.port)

            env = PisaEnv(
                port=self.port,
                isa_path=ISABELLE_PATH,
                starter_string=theory_file,
                working_directory=working_dir,
            )

            assert env.successful_starting, "Failed to initialize PisaEnv"

            obs, done, _, _ = env.step_to_top_level_state(
                'lemma test: "x + 0 = x" by simp', "default", "lemma1"
            )
            assert not done, "Proof should not be finished yet"
            assert "error" not in obs.lower(), f"Step failed: {obs}"

        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


class TestPisaStepEnv:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        self.port = 19998
        kill_port_process(self.port)
        yield
        kill_port_process(self.port)

    def test_pisa_step_env_init(self):
        from utils.pisa_client import PisaStepEnv

        theory_file = "theory Interactive\nimports Complex_Main\nbegin\n"
        working_dir = f"{ISABELLE_PATH}/src/HOL"

        process = subprocess.Popen(
            ["java", "-jar", PISA_JAR_PATH, str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            wait_for_port(self.port, timeout=60)

            env = PisaStepEnv(
                port=self.port,
                isa_path=ISABELLE_PATH,
                theory_file=theory_file,
                working_dir=working_dir,
                use_heuristic=False,
                use_hammer=False,
            )

            assert env.successful_starting, "Failed to initialize PisaStepEnv"

            res = env.step('lemma test: "x + 0 = x" by simp', "default", "lemma1")
            assert res["done"], f"Proof should be finished: {res}"
            assert not res["error"], f"Step failed: {res.get('error')}"

        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

    def test_step_to_target(self):
        from utils.pisa_client import PisaStepEnv

        working_dir = f"{L4V_PATH}/lib/Word_Lib"
        theory_file = f"{working_dir}/More_Arithmetic.thy"

        if not Path(theory_file).exists():
            pytest.skip(f"Theory file not found: {theory_file}")

        process = subprocess.Popen(
            ["java", "-jar", PISA_JAR_PATH, str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            wait_for_port(self.port, timeout=60)

            env = PisaStepEnv(
                port=self.port,
                isa_path=ISABELLE_PATH,
                theory_file=theory_file,
                working_dir=working_dir,
                use_heuristic=False,
                use_hammer=False,
            )

            assert env.successful_starting, "Failed to initialize PisaStepEnv"

            target = 'lemma min_pm [simp]: "min a b + (a - b) = a"\n'
            res = env.step(target, "default", "min_pm")

            assert not res["error"], f"Step to target failed: {res.get('error')}"

            done = env.is_finished("min_pm")
            assert done, "Target lemma should be finished"

        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

    def test_clone_and_focus_tls(self):
        from utils.pisa_client import PisaStepEnv

        working_dir = f"{L4V_PATH}/lib/Word_Lib"
        theory_file = f"{working_dir}/More_Arithmetic.thy"

        if not Path(theory_file).exists():
            pytest.skip(f"Theory file not found: {theory_file}")

        process = subprocess.Popen(
            ["java", "-jar", PISA_JAR_PATH, str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            wait_for_port(self.port, timeout=60)

            env = PisaStepEnv(
                port=self.port,
                isa_path=ISABELLE_PATH,
                theory_file=theory_file,
                working_dir=working_dir,
                use_heuristic=False,
                use_hammer=False,
            )

            target = 'lemma min_pm [simp]: "min a b + (a - b) = a"\n'
            res = env.step(target, "default", "min_pm")
            assert not res["error"], f"Step to target failed: {res.get('error')}"

            env.clone_to_new_name("min_pm", "state0")

            res1 = env.step("by arith", "min_pm", "min_pm_proved")
            env.clone_to_new_name("min_pm_proved", "state1")

            obs0 = env.get_state("state0")
            obs1 = env.get_state("min_pm")

            assert obs0 == obs1, "Cloned state should match original"

            env.del_state("state0")
            env.del_state("state1")
            env.del_state("min_pm")
            env.del_state("min_pm_proved")

        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


class TestWellFormedSI:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        self.port = 19997
        kill_port_process(self.port)
        yield
        kill_port_process(self.port)

    def test_init_wellformed_si(self):
        from utils.pisa_client import PisaStepEnv

        thy_file = Path(L4V_PATH) / "sys-init/WellFormed_SI.thy"
        if not thy_file.exists():
            pytest.skip(f"Theory file not found: {thy_file}")

        working_dir = str(thy_file.parent)
        theory_file = str(thy_file)

        process = subprocess.Popen(
            ["java", "-jar", PISA_JAR_PATH, str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            wait_for_port(self.port, timeout=60)

            env = PisaStepEnv(
                port=self.port,
                isa_path=ISABELLE_PATH,
                theory_file=theory_file,
                working_dir=working_dir,
                use_heuristic=False,
                use_hammer=False,
            )

            assert env.successful_starting, (
                "Failed to initialize PisaStepEnv with WellFormed_SI"
            )

        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


class TestMoreArithmetic:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        self.port = 19996
        kill_port_process(self.port)
        yield
        kill_port_process(self.port)

    def test_init_more_arithmetic(self):
        from utils.pisa_client import PisaStepEnv

        thy_file = Path(L4V_PATH) / "lib/Word_Lib/More_Arithmetic.thy"
        if not thy_file.exists():
            pytest.skip(f"Theory file not found: {thy_file}")

        working_dir = str(thy_file.parent)
        theory_file = str(thy_file)

        process = subprocess.Popen(
            ["java", "-jar", PISA_JAR_PATH, str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            wait_for_port(self.port, timeout=60)

            env = PisaStepEnv(
                port=self.port,
                isa_path=ISABELLE_PATH,
                theory_file=theory_file,
                working_dir=working_dir,
                use_heuristic=False,
                use_hammer=False,
            )

            assert env.successful_starting, (
                "Failed to initialize PisaStepEnv with More_Arithmetic"
            )

            target = 'lemma min_pm [simp]: "min a b + (a - b) = a"\n'
            res = env.step(target, "default", "min_pm")

            assert not res["error"], f"Step to target failed: {res.get('error')}"

            done = env.is_finished("min_pm")
            assert done, "Target lemma should be finished"

        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
