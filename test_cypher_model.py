"""
Test the fine-tuned Cypher generation model.

Usage:
    python test_cypher_model.py <checkpoint_path>
    python test_cypher_model.py tinker://your-run-id/sampler_weights/final
"""

import asyncio
import json
import sys
import os
import tinker
from tinker_cookbook.tokenizer_utils import get_tokenizer
from tinker_cookbook import renderers
from neo4j import GraphDatabase
from dotenv import load_dotenv


def execute_cypher_query(driver, database: str, query: str):
    """Execute a Cypher query and return success status and error message if any."""
    try:
        with driver.session(database=database) as session:
            result = session.run(query)
            # Consume the result to ensure query executes
            records = list(result)
            return True, None, len(records)
    except Exception as e:
        return False, str(e), 0


async def test_cypher_model(checkpoint_path: str, model_name: str = "Qwen/Qwen3-8B"):
    """Test the fine-tuned Cypher generation model."""

    print("\n" + "="*80)
    print("🧪 Testing Cypher Generation Model")
    print("="*80)
    print(f"Model: {model_name}")
    print(f"Checkpoint: {checkpoint_path}")
    print("="*80 + "\n")

    # Load environment variables
    load_dotenv("/Users/adithyagiridharan/Desktop/PythonProjects/DataPipelines/llm-data-pipelines/.env")

    # Connect to Neo4j
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USERNAME")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    neo4j_database = os.getenv("NEO4J_DATABASE")

    print(f"Connecting to Neo4j at {neo4j_uri}...")
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    print("Connected to Neo4j!\n")

    # Load test data
    test_file = "/tmp/tinker-datasets/cypher_test.jsonl"
    print(f"Loading test data from {test_file}...")

    test_cases = []
    with open(test_file, 'r') as f:
        for line in f:
            data = json.loads(line)
            question = data['messages'][0]['content']
            expected_cypher = data['messages'][1]['content']
            test_cases.append((question, expected_cypher))

    print(f"Loaded {len(test_cases)} test cases\n")

    # Create sampling client
    print("Loading fine-tuned model...")
    service_client = tinker.ServiceClient()
    try:
        sampling_client = service_client.create_sampling_client(
            base_model=model_name,
            model_path=checkpoint_path
        )
    except Exception as e:
        print(f"❌ Failed to load checkpoint: {e}")
        print(f"   Checkpoint: {checkpoint_path}")
        return

    tokenizer = get_tokenizer(model_name)
    renderer = renderers.get_renderer("qwen3", tokenizer)

    print("Model loaded successfully!\n")
    print("="*80)
    print("Running Test Cases")
    print("="*80 + "\n")

    # Test each case
    results = []
    for i, (question, expected_cypher) in enumerate(test_cases, 1):
        # Build prompt
        model_input = renderer.build_generation_prompt([
            renderers.Message(role="user", content=question)
        ])

        # Sample from model
        params = tinker.SamplingParams(
            max_tokens=512,
            temperature=0.0,
            stop=renderer.get_stop_sequences()
        )

        result = await sampling_client.sample_async(
            prompt=model_input,
            sampling_params=params,
            num_samples=1
        )

        # Parse response
        response = renderer.parse_response(result.sequences[0].tokens)[0]
        predicted_cypher = response['content'].strip()

        # Simple exact match check
        exact_match = predicted_cypher == expected_cypher

        # Calculate similarity (simple character-level)
        similarity = calculate_similarity(predicted_cypher, expected_cypher)

        # Execute the predicted query against Neo4j
        pred_success, pred_error, pred_records = execute_cypher_query(
            driver, neo4j_database, predicted_cypher
        )

        # Execute the expected query for comparison
        exp_success, exp_error, exp_records = execute_cypher_query(
            driver, neo4j_database, expected_cypher
        )

        results.append({
            'question': question,
            'expected': expected_cypher,
            'predicted': predicted_cypher,
            'exact_match': exact_match,
            'similarity': similarity,
            'predicted_executes': pred_success,
            'predicted_error': pred_error,
            'predicted_record_count': pred_records,
            'expected_executes': exp_success,
            'expected_record_count': exp_records
        })

        # Print result
        status = "✓" if exact_match else "≈" if similarity > 0.8 else "✗"
        exec_status = "✓" if pred_success else "✗"
        print(f"{status} Test {i}/{len(test_cases)} | Execution: {exec_status}")
        print(f"  Question: {question[:70]}...")
        if exact_match:
            print(f"  ✓ Exact match!")
        else:
            print(f"  Similarity: {similarity:.1%}")
            if similarity < 0.8:
                print(f"  Expected:  {expected_cypher[:80]}...")
                print(f"  Predicted: {predicted_cypher[:80]}...")

        # Print execution results
        if pred_success:
            print(f"  ✓ Query executed successfully ({pred_records} records)")
        else:
            print(f"  ✗ Query failed: {pred_error[:100]}")

        print()

    # Calculate metrics
    exact_matches = sum(1 for r in results if r['exact_match'])
    avg_similarity = sum(r['similarity'] for r in results) / len(results)
    high_similarity = sum(1 for r in results if r['similarity'] > 0.8)
    successful_executions = sum(1 for r in results if r['predicted_executes'])
    expected_executions = sum(1 for r in results if r['expected_executes'])

    print("="*80)
    print("📊 Test Results")
    print("="*80)
    print(f"Total test cases: {len(test_cases)}")
    print(f"\nSyntactic Accuracy:")
    print(f"  Exact matches: {exact_matches} ({100*exact_matches/len(test_cases):.1f}%)")
    print(f"  High similarity (>80%): {high_similarity} ({100*high_similarity/len(test_cases):.1f}%)")
    print(f"  Average similarity: {avg_similarity:.1%}")
    print(f"\nQuery Execution:")
    print(f"  Predicted queries executed: {successful_executions}/{len(test_cases)} ({100*successful_executions/len(test_cases):.1f}%)")
    print(f"  Expected queries executed: {expected_executions}/{len(test_cases)} ({100*expected_executions/len(test_cases):.1f}%)")
    print("="*80 + "\n")

    # Show some examples
    print("📝 Sample Predictions:\n")
    for i, result in enumerate(results[:3], 1):
        print(f"Example {i}:")
        print(f"Q: {result['question']}")
        print(f"Expected: {result['expected'][:100]}...")
        print(f"Predicted: {result['predicted'][:100]}...")
        print(f"Match: {'✓' if result['exact_match'] else '✗'} (Similarity: {result['similarity']:.1%})")
        print(f"Executes: {'✓' if result['predicted_executes'] else '✗'}", end="")
        if result['predicted_executes']:
            print(f" ({result['predicted_record_count']} records)")
        else:
            print(f" - Error: {result['predicted_error'][:60]}...")
        print()

    # Close Neo4j connection
    driver.close()
    print("Neo4j connection closed.")


def calculate_similarity(s1: str, s2: str) -> float:
    """Calculate simple character-level similarity between two strings."""
    if not s1 or not s2:
        return 0.0

    # Normalize whitespace
    s1 = ' '.join(s1.split())
    s2 = ' '.join(s2.split())

    # Simple character-level matching
    min_len = min(len(s1), len(s2))
    max_len = max(len(s1), len(s2))

    if max_len == 0:
        return 1.0

    matches = sum(1 for a, b in zip(s1, s2) if a == b)
    return matches / max_len


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_cypher_model.py <checkpoint_path> [model_name]")
        print("\nExample:")
        print("  python test_cypher_model.py tinker://abc123/sampler_weights/final")
        sys.exit(1)

    checkpoint = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "Qwen/Qwen3-8B"

    asyncio.run(test_cypher_model(checkpoint, model))
