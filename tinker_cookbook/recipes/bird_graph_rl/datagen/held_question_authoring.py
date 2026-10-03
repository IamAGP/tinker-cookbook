"""Bind individually authored held-out sentences to the frozen selected queue."""
import json
from . import question_authoring as binding
binding.QUEUE=[json.loads(l) for l in (binding.OUT/'heldout_question_queue.jsonl').read_text().splitlines()]
d=binding.d;m=binding.m;p=binding.p;field=binding.field
associated=binding.associated;comparison=binding.comparison
append_batch=binding.append_batch
QUEUE=binding.QUEUE;KNOWN=binding.KNOWN
