import asyncio
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from hashlib import file_digest
from importlib import import_module
from pathlib import Path
from threading import Event
from typing import Any, Protocol, cast

from pydantic import BaseModel

from repobrain.graph.exploration import ExplorationError

DIMENSION = 768
BATCH_SIZE = 8
MAX_TOKENS = 512
MAX_INPUT_BYTES = 8192
INFERENCE_TIMEOUT = 60
MAX_WAITING = 2


class EmbeddingModel(BaseModel, frozen=True):
    model_id: str
    revision: str
    dimension: int
    encoding_policy: str


MODEL = EmbeddingModel(
    model_id="jinaai/jina-embeddings-v2-base-code",
    revision="516f4baf13dec4ddddda8631e019b5737c8bc250",
    dimension=DIMENSION,
    encoding_policy="onnx-int8-mean-l2-512-v1",
)
TOKENIZER_SHA = "b01c78a902aa4facb2f47f95449f48e2f7bbfea5d2472ee2f6ce92323c6f86e5"
ONNX_SHA = "ed45870251c9f0cf656e78aab0d37a23489066df8a222bb1c8caf8a45f2cb16d"
ASSETS = {"tokenizer.json": TOKENIZER_SHA, "model_quantized.onnx": ONNX_SHA}


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> EmbeddingModel: ...

    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]: ...


def unavailable(message: str) -> ExplorationError:
    return ExplorationError(503, "embedding_unavailable", message)


def normalize(
    vectors: list[list[float]], expected: int, dimension: int
) -> list[list[float]]:
    error = ExplorationError(
        503, "invalid_embedding", "Embedding provider returned invalid vectors"
    )
    if len(vectors) != expected:
        raise error
    normalized = []
    for vector in vectors:
        if len(vector) != dimension or not all(
            math.isfinite(value) for value in vector
        ):
            raise error
        # Scale before computing the norm to handle extreme finite values.
        scale = max(map(abs, vector), default=0)
        if not scale:
            raise error
        scaled = [value / scale for value in vector]
        length = math.hypot(*scaled)
        normalized.append([value / length for value in scaled])
    return normalized


def require_assets(directory: Path) -> None:
    for filename, digest in ASSETS.items():
        try:
            with (directory / filename).open("rb") as stream:
                actual = file_digest(stream, "sha256").hexdigest()
        except OSError:
            raise unavailable(
                "Pinned local model weights and tokenizer are required"
            ) from None
        if actual != digest:
            raise unavailable("Local model asset failed integrity verification")


@dataclass
class Inference:
    cancelled: Event = field(default_factory=Event)
    options: Any = None

    def stop(self) -> None:
        self.cancelled.set()
        if self.options is not None:
            self.options.terminate = True


class LocalOnnxProvider:
    model = MODEL

    def __init__(self, directory: Path | None) -> None:
        self.directory = directory
        self.runtime: tuple[Any, Any, Any, Any] | None = None
        self.task: asyncio.Task[list[list[float]]] | None = None
        self.serial = asyncio.Lock()
        self.admitted = 0

    def load(self) -> tuple[Any, Any, Any, Any]:
        if self.directory is None:
            raise unavailable(
                "Configure a directory containing the pinned local model assets"
            )
        require_assets(self.directory)
        try:
            numpy = import_module("numpy")
            ort = import_module("onnxruntime")
            tokenizer = import_module("tokenizers").Tokenizer.from_file(
                str(self.directory / "tokenizer.json")
            )
        except ImportError:
            raise unavailable(
                "Install the optional vector inference dependencies"
            ) from None
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(
            str(self.directory / "model_quantized.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        return numpy, ort, tokenizer, session

    def infer(self, texts: list[str], job: Inference) -> list[list[float]]:
        try:
            if self.runtime is None:
                self.runtime = self.load()
            numpy, ort, tokenizer, session = self.runtime
            encoded = tokenizer.encode_batch(texts)
            all_inputs = {
                "input_ids": numpy.asarray(
                    [item.ids for item in encoded], dtype=numpy.int64
                ),
                "attention_mask": numpy.asarray(
                    [item.attention_mask for item in encoded], dtype=numpy.int64
                ),
                "token_type_ids": numpy.asarray(
                    [item.type_ids for item in encoded], dtype=numpy.int64
                ),
            }
            inputs = {item.name: all_inputs[item.name] for item in session.get_inputs()}
            options = ort.RunOptions()
            job.options = options
            if job.cancelled.is_set():
                raise unavailable("Embedding inference cancelled")
            hidden = session.run(["last_hidden_state"], inputs, options)[0]
            mask = all_inputs["attention_mask"][..., None]
            if hidden.shape != (*mask.shape[:2], DIMENSION):
                raise unavailable("Pinned model returned an unexpected output shape")
            pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1)
            return cast(list[list[float]], pooled.tolist())
        except ExplorationError:
            raise
        except Exception:
            raise unavailable("Local embedding inference failed") from None

    async def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not 1 <= len(texts) <= BATCH_SIZE or any(
            len(text.encode()) > MAX_INPUT_BYTES for text in texts
        ):
            raise unavailable("Embedding input exceeds the batch or byte limit")
        if self.admitted >= 1 + MAX_WAITING:
            raise unavailable("Local embedding provider is busy")
        self.admitted += 1
        job: Inference | None = None
        try:
            async with asyncio.timeout(INFERENCE_TIMEOUT):
                await self.serial.acquire()
                job = Inference()
                task = asyncio.create_task(
                    asyncio.to_thread(self.infer, list(texts), job)
                )
                self.task = task
                task.add_done_callback(self.finish)
                return await asyncio.shield(task)
        except TimeoutError:
            if job is not None:
                job.stop()
            raise unavailable("Local embedding inference timed out") from None
        except asyncio.CancelledError:
            if job is not None:
                job.stop()
            raise
        finally:
            if job is None:
                self.admitted -= 1

    def finish(self, task: asyncio.Task[list[list[float]]]) -> None:
        # The native call owns the slot even after its caller has left.
        if not task.cancelled():
            task.exception()
        self.task = None
        self.admitted -= 1
        self.serial.release()

    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self.encode(texts)

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return await self.encode(texts)
