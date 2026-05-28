import asyncio
import tinker
from tinker_cookbook.tokenizer_utils import get_tokenizer
from tinker_cookbook import renderers

async def test_distilled_model():
    # Your trained checkpoint
    checkpoint_path = "tinker://7508c76a-9087-468d-9975-ad3b2c9c0ee1/sampler_weights/final"
    model_name = "Qwen/Qwen3-30B-A3B"

    print("Loading distilled model...")
    service_client = tinker.ServiceClient()
    sampling_client = service_client.create_sampling_client(
        base_model=model_name,
        model_path=checkpoint_path
    )

    tokenizer = get_tokenizer(model_name)
    renderer = renderers.get_renderer("qwen3", tokenizer)

    # Test cases (WITHOUT the long prompt!)
    test_cases = [
        ("一生、バンドしてくれる？", "ja"),
        ("Bonjour, comment allez-vous?", "fr"),
        ("Hello, how are you?", "en"),
        ("Hola, ¿cómo estás?", "es"),
        ("Привет, как дела?", "ru"),
        ("مرحبا، كيف حالك؟", "ar"),
        ("Hallo, wie geht es dir?", "de"),
        ("你好吗？", "zh"),
        ("Xin chào, bạn khỏe không?", "vi"),
        ("नमस्ते, आप कैसे हैं?", "hi"),
    ]

    print("\n" + "="*60)
    print("Testing Distilled Model (NO prompt needed!)")
    print("="*60 + "\n")

    correct = 0
    for sentence, expected in test_cases:
        # Just send the query - no long prompt!
        model_input = renderer.build_generation_prompt([
            renderers.Message(role="user", content=sentence)
        ])

        params = tinker.SamplingParams(
            max_tokens=10,
            temperature=0.0,
            stop=renderer.get_stop_sequences()
        )
        result = await sampling_client.sample_async(
            prompt=model_input,
            sampling_params=params,
            num_samples=1
        )

        response = renderer.parse_response(result.sequences[0].tokens)[0]
        predicted = response['content'].strip()

        is_correct = predicted == expected
        correct += is_correct

        status = "✓" if is_correct else "✗"
        print(f"{status} Input: {sentence[:40]}")
        print(f"  Expected: {expected} | Predicted: {predicted}")
        print()

    accuracy = 100 * correct / len(test_cases)
    print("="*60)
    print(f"Accuracy: {correct}/{len(test_cases)} ({accuracy:.1f}%)")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_distilled_model())
