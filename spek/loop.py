"""Generate-verify-repair loop driving an external agent command."""

import subprocess


class Loop:
    def __init__(self, spec, impl_path, agent_cmd, max_rounds=3):
        self.spec = spec
        self.impl_path = impl_path
        self.agent_cmd = agent_cmd
        self.max_rounds = max_rounds

    def run(self):
        from spek.prompt import PromptGenerator
        for round_num in range(self.max_rounds + 1):
            prompt = PromptGenerator(self.spec).generation_prompt()
            result = subprocess.run(self.agent_cmd, input=prompt, capture_output=True, text=True, shell=True)
            if result.returncode != 0:
                return False
            # TODO: actually verify and loop on failure
            return True
        return False
