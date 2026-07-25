# FoodMind AI

## Project Overview

FoodMind AI is an Agentic Food Knowledge Assistant.

The project is being developed as an end-to-end LLM engineering portfolio project.

The initial goal is to build a production-quality Agentic RAG application around recipes, ingredients, nutrition and culinary knowledge.

The project must be implemented incrementally.

The architecture should allow evolving from a simple retrieval system into a multi-agent system without changing the domain layer.

---

# Technology Stack

Backend

- Python 3.13+
- FastAPI
- Pydantic v2
- PydanticAI
- pydantic-graph (future multi-agent orchestration)

Search

- Elasticsearch
- BM25
- Dense Vector Search
- Hybrid Search (RRF)

Frontend

- Streamlit

Observability

- Logfire

Deployment

- Docker Compose

Testing

- pytest

---

# Project Goals

The assistant should answer questions about:

- recipes
- ingredients
- substitutions
- nutrition
- allergens
- diets
- cuisines
- cooking techniques
- food safety

Example questions:

- What can I cook with chicken and mushrooms?
- Suggest vegan recipes under 500 kcal.
- Replace butter in baking.
- Is this recipe gluten-free?
- Which recipes are high in protein?

---

# High-Level Development Roadmap

The project must be developed in phases.

## Phase 1

Data Retrieval Foundation

This phase is the highest priority.

Before implementing any AI agents we must:

- evaluate datasets
- validate licenses
- download datasets
- create reproducible ingestion pipelines
- normalize data
- generate embeddings
- store searchable documents in Elasticsearch

The first milestone is NOT an AI assistant.

The first milestone is a high-quality searchable knowledge corpus.

---

## Phase 2

Retrieval

Implement and compare:

- BM25
- Dense Vector Search
- Hybrid Search
- Metadata Filtering
- Optional Reranking

Evaluate:

- Recall@K
- HitRate
- MRR
- nDCG
- Latency

Only after retrieval quality is acceptable continue.

---

## Phase 3

Basic RAG

Implement a classical RAG pipeline:

User Query

↓

Hybrid Retrieval

↓

Context Builder

↓

LLM

↓

Answer

Evaluate against retrieval metrics.

This becomes the baseline.

---

## Phase 4

Single-Agent Application

Introduce PydanticAI.

Responsibilities:

- reasoning
- tool selection
- structured output

The agent should NEVER perform deterministic logic.

Deterministic logic remains inside Python services.

The agent should use typed tools.

---

## Phase 5

Production Application

FastAPI

Streamlit

Monitoring

Evaluation

Docker

Deployment

---

## Phase 6

Multi-Agent Architecture

Replace the single agent with pydantic-graph.

Expected architecture:

Supervisor

↓

Recipe Agent

Nutrition Agent

Safety Agent

Knowledge Agent

↓

Reviewer Agent

The existing domain services must remain unchanged.

Only orchestration changes.

---

# Architecture Principles

The project follows Clean Architecture.

Layers:

API

↓

Application

↓

Agent

↓

Domain Services

↓

Repositories

↓

Elasticsearch

Domain services must not depend on AI frameworks.

PydanticAI should only orchestrate existing services.

---

# Elasticsearch

Primary datastore.

Main indices:

food-recipes

food-entities

food-knowledge

ingestion-runs

Use aliases.

Documents should contain:

- searchable text
- structured metadata
- dense vectors
- source provenance

---

# Data Ingestion

Pipeline:

Source

↓

Download

↓

Raw Storage

↓

Parsing

↓

Validation

↓

Normalization

↓

Entity Resolution

↓

Enrichment

↓

Embedding Generation

↓

Bulk Indexing

↓

Elasticsearch

Every ingestion must produce a report.

---

# Domain Models

Core entities:

Recipe

Ingredient

RecipeIngredient

KnowledgeDocument

Nutrition

Substitution

Allergen

SourceReference

All entities use stable IDs.

Example:

recipe:foodcom:12345

ingredient:internal:chickpea

knowledge:wikibooks:braising

---

# Coding Guidelines

Prefer:

- small modules
- typed Python
- Pydantic models
- async APIs
- dependency injection
- repository pattern

Avoid:

- business logic inside API routes
- Elasticsearch queries inside AI agents
- AI-generated numeric values
- duplicated logic

---

# Development Strategy

Always build from the bottom up.

Order of implementation:

1. Data sources
2. Ingestion
3. Elasticsearch
4. Retrieval
5. Evaluation
6. Basic RAG
7. PydanticAI
8. FastAPI
9. Streamlit
10. Multi-agent

Do not skip phases.

Each phase should be independently testable.

---

# Long-Term Goal

The final system should become a production-quality Agentic Food Knowledge Platform capable of evolving into a multi-agent architecture without changing the underlying domain model or repositories.