"""Execute pinned author components without importing their unused GPU/model stack.

AST selection compiles the actual original definition, unchanged. Each selected
source segment is hashed. This is a component reproduction, not running the
entire author's notebook or main script.
"""
import ast
import contextlib
import hashlib
import io
import json
import random
import sys
from pathlib import Path


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def original_definition(path, name, namespace):
    source = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name)
    snippet = ast.get_source_segment(source, node)
    compiled = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(compiled)
    exec(compile(compiled, path, "exec"), namespace)
    return namespace[name], {"source_path": path, "definition": name, "sha256": sha(snippet), "line": node.lineno}


def jailguard_variants(payload):
    import numpy as np
    sys.path.insert(0, "/task/JailGuard/utils")
    import mask_utils
    namespace = {"mask_text": mask_utils.mask_text}
    mutator, provenance = original_definition("/task/JailGuard/utils/augmentations.py", "rand_replace_text", namespace)
    random.seed(payload["seed"])
    np.random.seed(payload["seed"])
    variants = []
    for example_index, example in enumerate(payload["examples"]):
        random.seed(payload["seed"] + example_index)
        np.random.seed(payload["seed"] + example_index)
        original = example["input"]
        for repeat in range(payload["variants"]):
            if isinstance(original, str):
                mutated = "".join(mutator([original]))
                # Match the original main_txt.py load_dirs / literal-line-join behavior.
                prompt = r"\n".join(mutated.splitlines(keepends=True))
                output = {"id": f"{example['id']}:variant:{repeat}", "source_id": example["id"], "prompt": prompt,
                          "example_seed": payload["seed"] + example_index}
            else:
                # Preserve role structure for historical prompt-injection samples.
                messages = [
                    {**message, "content": "".join(mutator([message["content"]]))}
                    for message in original
                ]
                output = {"id": f"{example['id']}:variant:{repeat}", "source_id": example["id"], "messages": messages,
                          "example_seed": payload["seed"] + example_index}
            variants.append(output)
    return {"kind": "original-author-RR-component", "variants": variants, "source": provenance,
            "settings": {"mutator": "RR", "level": 0.01, "variants": payload["variants"], "seed": payload["seed"]},
            "adaptation": "Unmodified selected text mutator loaded without unrelated torchvision image code."}


def jailguard_detect(payload):
    import spacy
    sys.path.insert(0, "/task/JailGuard/utils")
    import utils as upstream_utils
    metric = spacy.load("en_core_web_md")
    rows = []
    for source_id, texts in payload["responses"].items():
        directory = Path("/tmp/detection") / source_id.replace(":", "-")
        directory.mkdir(parents=True)
        with contextlib.redirect_stdout(io.StringIO()):
            divergence, blocked = upstream_utils.update_divergence(
                texts, "dataset.pkl", str(directory), select_number=len(texts), metric=metric,
            )
            decision = upstream_utils.detect_attack(divergence, blocked, payload["threshold"])
        rows.append({"source_id": source_id, "variant_responses": len(texts),
                     "max_divergence": float(divergence), "all_refused": bool(blocked[0]),
                     "minimum_refusal_keywords": int(blocked[1]), "detected_attack": bool(decision)})
    paths = ["/task/JailGuard/utils/utils.py", "/task/JailGuard/utils/similarity.py"]
    return {
        "kind": "original-author-detector-component", "results": rows,
        "embedding_model": "en_core_web_md-3.7.1", "spacy_version": spacy.__version__,
        "threshold": payload["threshold"], "variant_count": payload["variants"],
        "sources": {path: sha(Path(path).read_text()) for path in paths},
        "adaptation": "Actual author KL-divergence, similarity and refusal logic on Azure Sol responses; not published GPT-3.5 accuracy.",
    }


def mucoco_humaneval(payload):
    import typing
    namespace = {"ast": ast, "random": random, "Dict": typing.Dict, "Tuple": typing.Tuple,
                 "Iterable": typing.Iterable, "Seed": type("Seed", (), {"value": 1234})}
    helper, source = original_definition("/task/code_mutation/ast_mutation.py", "ASTNodeHelper", namespace)
    rows = []
    for example in payload["examples"]:
        problem = example["payload"]
        program = problem["prompt"] + problem["canonical_solution"]
        tree = ast.parse(program)
        # Select a real local identifier, never the function API or parameter.
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
        arguments = {argument.arg for argument in function.args.args}
        local_ids = [node.id for node in ast.walk(function) if isinstance(node, ast.Name)
                     and isinstance(node.ctx, ast.Store) and node.id not in arguments]
        if not local_ids:
            rows.append({"task_id": problem["task_id"], "status": "invalid_variant", "reason": "No local variable"})
            continue
        old = local_ids[0]
        transformed = helper.VariableNameTransformer({old: "audit_local"}).visit(ast.parse(program))
        ast.fix_missing_locations(transformed)
        variant = ast.unparse(transformed) + "\n"
        outputs = []
        for label, candidate in (("original", program), ("rename", variant)):
            scope = {}
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(candidate + "\n" + problem["test"], "<benchmark>", "exec"), scope)
                    scope["check"](scope[problem["entry_point"]])
                outputs.append({"condition": label, "passed": True})
            except Exception as error:
                outputs.append({"condition": label, "passed": False, "error": type(error).__name__ + ": " + str(error)})
        rows.append({"task_id": problem["task_id"], "status": "validated" if all(row["passed"] for row in outputs) else "failed",
                     "original_sha256": sha(program), "variant_sha256": sha(variant), "rename": {old: "audit_local"},
                     "outputs": outputs, "variant_code": variant})
    return {"kind": "original-MUCOCO-transformer-on-HumanEval", "results": rows, "source": source,
            "adaptation": "Actual VariableNameTransformer class; bypass unused constants/model imports. Canonical solutions, no model-generation claims."}


def jailguard_original_replay(payload):
    """Execute main_txt.py itself. No network; bridge responses must match exact queries."""
    import os
    import runpy
    import types
    import numpy as np
    from collections import defaultdict
    os.chdir("/task/JailGuard")
    sys.path.insert(0, "/task/JailGuard/utils")
    # Unused image dependency only. No text mutation/detection function is replaced.
    image_stub = types.ModuleType("torchvision")
    image_stub.__path__ = []
    transforms_stub = types.ModuleType("torchvision.transforms")
    image_stub.transforms = transforms_stub
    sys.modules["torchvision"] = image_stub
    sys.modules["torchvision.transforms"] = transforms_stub
    import utils as upstream_utils
    responses = defaultdict(list)

    def key(prompt=None, messages=None):
        if messages is not None:
            normalized = [
                {**message, "content": "".join(message["content"]) if isinstance(message["content"], list) else message["content"]}
                for message in messages
            ]
            return sha(json.dumps(normalized, sort_keys=True))
        return sha(prompt)

    for variant in payload["responses"]:
        responses[key(variant.get("prompt"), variant.get("messages"))].append(variant["response"])
    called = []

    def replay_query(version, question, sleep=3, add_question="", messages=None, **kwargs):
        query_key = key(question, messages)
        if not responses[query_key]:
            raise RuntimeError(f"Original-script query does not match frozen live response: {query_key}")
        called.append(query_key)
        return responses[query_key].pop(0)

    upstream_utils.query_gpt = replay_query
    outputs = []
    script_source = Path("/task/JailGuard/main_txt.py").read_text()
    compatibility_change = (
        "save_name=name_list[j]",
        "save_name=name_list[j].removesuffix('.pkl') + '.txt'",
    )
    assert script_source.count(compatibility_change[0]) == 1
    compatibility_source = script_source.replace(*compatibility_change)
    for example_index, example in enumerate(payload["examples"]):
        random.seed(example["seed"])
        np.random.seed(example["seed"])
        run_dir = Path("/tmp/original-replay") / example["id"].replace(":", "-")
        sys.argv = [
            "main_txt.py", "--mutator", "RR", "--serial_num", str(example["serial"]),
            "--path", "/task/dataset/text/dataset.pkl", "--number", "8",
            "--variant_save_dir", str(run_dir / "variants"),
            "--response_save_dir", str(run_dir / "responses"),
        ]
        captured = io.StringIO()
        before = len(called)
        with contextlib.redirect_stdout(captured):
            if example_index < 2:
                runpy.run_path("/task/JailGuard/main_txt.py", run_name="__main__")
            else:
                # One filename-only compatibility fix. Without it original message-list
                # responses inherit .pkl names and are excluded by read_file_list.
                # The original checkout is never changed.
                scope = {"__name__": "__main__", "__file__": "/task/JailGuard/main_txt.py"}
                exec(compile(compatibility_source, "<JailGuard-main-filename-compatibility>", "exec"), scope)
        outputs.append({"source_id": example["id"], "replayed_queries": len(called)-before,
                        "script_stdout": captured.getvalue().strip(),
                        "variant_files": len(list((run_dir / "variants").iterdir())),
                        "script_mode": "original-unmodified" if example_index < 2 else "one-line-filename-compatibility"})
    unused = sum(len(values) for values in responses.values())
    return {
        "kind": "actual-author-main-script-frozen-response-replay",
        "original_script_sha256": sha(Path("/task/JailGuard/main_txt.py").read_text()),
        "compatibility_script_sha256": sha(compatibility_source),
        "compatibility_diff": {"old": compatibility_change[0], "new": compatibility_change[1]},
        "results": outputs, "matched_queries": len(called), "unused_responses": unused,
        "all_queries_matched": len(called) == len(payload["responses"]) and unused == 0,
        "synthetic_selftest": bool(payload.get("synthetic_selftest", False)),
        "adaptations": [
            "GPT-3.5 provider calls bridged to previously captured Azure GPT-6.1 Sol responses matched by exact query hash.",
            "Historical message content lists normalized to text at the provider boundary.",
            "Unused torchvision image dependency stubbed; actual RR text mutator and detector unchanged.",
            "Two benign inputs run the unmodified main script. Two message-list inputs need one response-filename fix because .pkl responses are skipped by the original scorer.",
            "Python 3.12 / spaCy 3.7.5 instead of the historical full image/text dependency environment.",
            "No published accuracy replication claim from four inputs.",
        ],
    }


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    command = payload["command"]
    result = {
        "jailguard-variants": jailguard_variants,
        "jailguard-detect": jailguard_detect,
        "mucoco-humaneval": mucoco_humaneval,
        "jailguard-original-replay": jailguard_original_replay,
    }[command](payload)
    print(json.dumps(result))
