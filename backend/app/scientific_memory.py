"""Deterministic scientific memory engine for ResearchOS."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.config import Settings, get_settings
from app.global_knowledge_graph import KnowledgeGraphService
from app.storage import SQLiteStore
from app.workflow_engine import WorkflowEngine


@dataclass
class ScientificMemoryService:
    """Relate new experiments to historical ResearchOS work.

    This deterministic implementation is intentionally transparent. It builds
    feature vectors from existing provider metadata and can later be replaced or
    augmented with embeddings, graph neural networks, or contrastive learning.
    """

    settings: Settings | None = None
    store: SQLiteStore | None = None
    knowledge_graph: KnowledgeGraphService | None = None
    workspace_id: str | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.store = self.store or SQLiteStore(settings=self.settings)
        self.knowledge_graph = self.knowledge_graph or KnowledgeGraphService(
            settings=self.settings,
            store=self.store,
            workspace_id=self.workspace_id,
        )

    def summary(self) -> dict[str, Any]:
        """Return memory index status."""

        memories = self.build()
        return {
            "experiment_count": len(memories),
            "memory_vector_count": len(memories),
            "feature_count": sum(len(item["feature_vector"]) for item in memories),
            "workspace_id": self.workspace_id,
            "top_memory_features": _top_features(memories),
            "message": "Scientific Memory uses deterministic feature similarity; embeddings can be added later.",
        }

    def build(self) -> list[dict[str, Any]]:
        """Build memory records for all workspace-scoped experiments."""

        experiments = self.store.list_experiments(workspace_id=self.workspace_id)
        return [self.experiment_memory(str(experiment["id"]), experiment=experiment) for experiment in experiments]

    def experiment_memory(self, experiment_id: str, experiment: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build one experiment memory payload."""

        experiment = experiment or self.store.get_experiment(experiment_id) or self.store.find_experiment_by_reference(experiment_id)
        if experiment is None:
            raise LookupError(f"Experiment not found: {experiment_id}")
        experiment_id = str(experiment["id"])
        graph = self.knowledge_graph.experiment_neighborhood(experiment_id) or {}
        assets = self.store.list_assets_for_experiment(experiment)
        workflow = WorkflowEngine(self.store).workflow_for_experiment(experiment)
        feature_vector = self._feature_vector(experiment, graph, assets, workflow)
        memory_vector = _normalize_counter(feature_vector)
        similarity_vector = sorted(memory_vector.items(), key=lambda item: (-item[1], item[0]))[:25]
        return {
            "experiment": experiment,
            "memory_vector": dict(memory_vector),
            "feature_vector": dict(feature_vector),
            "similarity_vector": [{"feature": key, "weight": value} for key, value in similarity_vector],
            "source_counts": {
                "assets": len(assets),
                "graph_entities": len(graph.get("entities") or []),
                "related_literature": len(graph.get("literature") or []),
                "images": len(graph.get("images") or []),
                "statistics": len(graph.get("statistics") or []),
                "workflow_history": len(workflow.get("history") or []),
            },
        }

    def find_similar_experiments(self, experiment_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return most similar historical experiments."""

        target = self.experiment_memory(experiment_id)
        target_id = str(target["experiment"]["id"])
        results = []
        for candidate in self.build():
            candidate_id = str(candidate["experiment"]["id"])
            if candidate_id == target_id:
                continue
            comparison = _compare_vectors(target["memory_vector"], candidate["memory_vector"])
            if comparison["score"] <= 0:
                continue
            results.append(
                {
                    "experiment": candidate["experiment"],
                    "similarity_score": comparison["score"],
                    "key_similarities": comparison["similarities"],
                    "important_differences": comparison["differences"],
                    "source_counts": candidate["source_counts"],
                }
            )
        return sorted(results, key=lambda item: (-float(item["similarity_score"]), str(item["experiment"].get("title") or "")))[:limit]

    def find_similar_protocols(self, experiment_id: str, limit: int = 5) -> list[dict[str, Any]]:
        return self._related_assets_by_type(experiment_id, {"protocol"}, limit)

    def find_similar_statistics(self, experiment_id: str, limit: int = 5) -> list[dict[str, Any]]:
        return self._related_assets_with_metadata_key(experiment_id, "statistics", limit)

    def find_similar_images(self, experiment_id: str, limit: int = 5) -> list[dict[str, Any]]:
        return self._related_assets_by_type(experiment_id, {"image", "microscopy"}, limit)

    def find_similar_literature(self, experiment_id: str, limit: int = 5) -> list[dict[str, Any]]:
        target = self.experiment_memory(experiment_id)
        target_terms = _feature_terms(target["feature_vector"], prefixes={"entity", "compound", "marker", "gene", "protein"})
        documents = [document for document in self.store.list_documents(workspace_id=self.workspace_id) if document.get("provider") == "literature"]
        scored = []
        for document in documents:
            detail = self.store.get_document(str(document["id"])) or document
            terms = _terms_from_text(f"{detail.get('title')} {detail.get('content', '')}")
            overlap = sorted(target_terms.intersection(terms))
            if overlap:
                scored.append({"document": detail, "similarity_score": min(1.0, len(overlap) / max(1, len(target_terms))), "key_similarities": overlap[:8]})
        return sorted(scored, key=lambda item: -float(item["similarity_score"]))[:limit]

    def similar_payload(self, experiment_id: str, limit: int = 5) -> dict[str, Any]:
        """Return full memory comparison response."""

        memory = self.experiment_memory(experiment_id)
        similar = self.find_similar_experiments(experiment_id, limit=limit)
        return {
            "experiment_id": experiment_id,
            "memory": memory,
            "most_similar_experiments": similar,
            "related_protocols": self.find_similar_protocols(experiment_id, limit=limit),
            "related_literature": self.find_similar_literature(experiment_id, limit=limit),
            "related_statistics": self.find_similar_statistics(experiment_id, limit=limit),
            "related_microscopy": self.find_similar_images(experiment_id, limit=limit),
            "method": "deterministic_feature_similarity",
            "limitations": [
                "No learned embeddings are used yet.",
                "Similarity depends on extracted metadata and provider coverage.",
                "Missing assets or sparse notebook fields reduce memory quality.",
            ],
        }

    def _feature_vector(
        self,
        experiment: dict[str, Any],
        graph: dict[str, Any],
        assets: list[dict[str, Any]],
        workflow: dict[str, Any],
    ) -> Counter[str]:
        features: Counter[str] = Counter()
        _add_list_features(features, "compound", experiment.get("compounds"))
        _add_list_features(features, "treatment", experiment.get("treatments"))
        _add_list_features(features, "concentration", experiment.get("concentrations"), weight=0.8)
        _add_list_features(features, "timepoint", experiment.get("time_points"), weight=0.8)
        _add_list_features(features, "marker", experiment.get("markers"))
        _add_list_features(features, "antibody", experiment.get("antibodies"), weight=0.8)
        _add_list_features(features, "imaging", experiment.get("imaging_methods"), weight=0.8)
        _add_list_features(features, "sequencing", experiment.get("sequencing"), weight=0.8)
        for key in ["cell_line", "organoid_batch", "researcher", "source_provider"]:
            if experiment.get(key):
                features[f"{key}:{_norm(experiment[key])}"] += 1.0
        for token in _terms_from_text(f"{experiment.get('title', '')} {experiment.get('notes', '')} {experiment.get('conclusions', '')}"):
            features[f"text:{token}"] += 0.25
        for entity in graph.get("entities") or []:
            if isinstance(entity, dict) and entity.get("name"):
                features[f"entity:{_norm(entity['name'])}"] += 0.9
                if entity.get("entity_type"):
                    features[f"{_norm(entity['entity_type'])}:{_norm(entity['name'])}"] += 0.9
        for asset in assets:
            asset_type = _norm(asset.get("asset_type") or "asset")
            provider = _norm(asset.get("provider") or "local")
            features[f"asset_type:{asset_type}"] += 0.5
            features[f"provider:{provider}"] += 0.4
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            if isinstance(metadata, dict):
                _add_list_features(features, "asset_marker", metadata.get("markers"), weight=0.8)
                if metadata.get("timepoint"):
                    features[f"asset_timepoint:{_norm(metadata['timepoint'])}"] += 0.7
                if metadata.get("statistics"):
                    features["has:statistics"] += 1.2
        if workflow.get("current_stage"):
            features[f"workflow:{_norm(workflow['current_stage'])}"] += 0.3
        return features

    def _related_assets_by_type(self, experiment_id: str, asset_types: set[str], limit: int) -> list[dict[str, Any]]:
        experiment = self.store.find_experiment_by_reference(experiment_id)
        if experiment is None:
            return []
        target_features = self.experiment_memory(str(experiment["id"]))["memory_vector"]
        candidates = []
        for asset in self.store.list_assets(workspace_id=self.workspace_id):
            if _norm(asset.get("asset_type")) not in asset_types and _norm(asset.get("provider")) not in asset_types:
                continue
            asset_features = Counter()
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            _add_list_features(asset_features, "asset_marker", metadata.get("markers") if isinstance(metadata, dict) else [], weight=1.0)
            for token in _terms_from_text(f"{asset.get('title', '')} {asset.get('filename', '')}"):
                asset_features[f"text:{token}"] += 0.5
            score = _compare_vectors(target_features, _normalize_counter(asset_features))["score"]
            candidates.append({"asset": asset, "similarity_score": score})
        return sorted(candidates, key=lambda item: -float(item["similarity_score"]))[:limit]

    def _related_assets_with_metadata_key(self, experiment_id: str, metadata_key: str, limit: int) -> list[dict[str, Any]]:
        related = []
        for asset in self.store.list_assets(workspace_id=self.workspace_id):
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            if isinstance(metadata, dict) and metadata.get(metadata_key):
                related.append({"asset": asset, "summary": metadata.get(metadata_key), "similarity_score": 0.5})
        return related[:limit]


def _add_list_features(features: Counter[str], prefix: str, values: object, weight: float = 1.0) -> None:
    if isinstance(values, str):
        iterable = [values]
    elif isinstance(values, list):
        iterable = values
    else:
        iterable = []
    for value in iterable:
        if value:
            features[f"{prefix}:{_norm(value)}"] += weight


def _normalize_counter(features: Counter[str]) -> dict[str, float]:
    magnitude = math.sqrt(sum(float(value) ** 2 for value in features.values()))
    if magnitude == 0:
        return {}
    return {key: round(float(value) / magnitude, 6) for key, value in features.items()}


def _compare_vectors(left: dict[str, float], right: dict[str, float]) -> dict[str, Any]:
    shared = sorted(set(left).intersection(right))
    score = round(sum(float(left[key]) * float(right[key]) for key in shared), 4)
    similarities = [_human_feature(key) for key in sorted(shared, key=lambda item: -(float(left[item]) + float(right[item])))[:10]]
    left_only = sorted(set(left).difference(right), key=lambda item: -float(left[item]))[:6]
    right_only = sorted(set(right).difference(left), key=lambda item: -float(right[item]))[:6]
    differences = [_human_feature(key) for key in [*left_only[:3], *right_only[:3]]]
    return {"score": score, "similarities": similarities, "differences": differences}


def _top_features(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for memory in memories:
        counter.update(memory.get("feature_vector") or {})
    return [{"feature": _human_feature(key), "weight": round(float(value), 3)} for key, value in counter.most_common(15)]


def _feature_terms(features: dict[str, float], prefixes: set[str]) -> set[str]:
    terms = set()
    for key in features:
        prefix, _, value = key.partition(":")
        if prefix in prefixes and value:
            terms.add(value)
    return terms


def _terms_from_text(text: str) -> set[str]:
    stop = {"the", "and", "with", "for", "from", "that", "this", "were", "was", "notes", "result"}
    return {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_+-]{2,}", text) if token.lower() not in stop}


def _human_feature(feature: str) -> str:
    return feature.replace("_", " ").replace(":", " = ")


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())
