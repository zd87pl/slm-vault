#!/bin/bash
# Comprehensive RunPod endpoint testing suite

set -e

# Configuration
ENDPOINT_URL="https://api.runpod.ai/v2/ayi3s70ihlpbtg"
RUNPOD_API_KEY="${RUNPOD_API_KEY}"

if [ -z "$RUNPOD_API_KEY" ]; then
    echo "Error: RUNPOD_API_KEY not set"
    echo "Usage: export RUNPOD_API_KEY=your-key"
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper function to submit job
submit_job() {
    local payload="$1"
    curl -s -X POST "${ENDPOINT_URL}/run" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
        -d "$payload" | jq -r '.id'
}

# Helper function to poll for completion
wait_for_job() {
    local job_id="$1"
    local max_wait="${2:-300}"  # Default 5 minutes
    local elapsed=0

    echo -n "Waiting for job $job_id..."

    while [ $elapsed -lt $max_wait ]; do
        local status=$(curl -s -X GET "${ENDPOINT_URL}/status/${job_id}" \
            -H "Authorization: Bearer ${RUNPOD_API_KEY}" | jq -r '.status')

        if [ "$status" == "COMPLETED" ]; then
            echo -e " ${GREEN}✓ COMPLETED${NC}"
            return 0
        elif [ "$status" == "FAILED" ]; then
            echo -e " ${RED}✗ FAILED${NC}"
            curl -s -X GET "${ENDPOINT_URL}/status/${job_id}" \
                -H "Authorization: Bearer ${RUNPOD_API_KEY}" | jq '.'
            return 1
        fi

        echo -n "."
        sleep 5
        elapsed=$((elapsed + 5))
    done

    echo -e " ${YELLOW}⏱ TIMEOUT${NC}"
    return 1
}

# Get job result
get_result() {
    local job_id="$1"
    curl -s -X GET "${ENDPOINT_URL}/status/${job_id}" \
        -H "Authorization: Bearer ${RUNPOD_API_KEY}"
}

echo ""
echo "========================================="
echo "RunPod WDVA Comprehensive Test Suite"
echo "========================================="
echo "Endpoint: $ENDPOINT_URL"
echo ""

# Track results
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Test 1: Basic Health Check
echo -e "${BLUE}[Test 1/8]${NC} Basic Health Check (No Adapter)"
TOTAL_TESTS=$((TOTAL_TESTS + 1))

JOB_ID=$(submit_job '{
    "input": {
        "task": "inference",
        "prompt": "Hello, how are you?",
        "max_tokens": 30
    }
}')

if wait_for_job "$JOB_ID" 120; then
    RESULT=$(get_result "$JOB_ID")
    RESPONSE=$(echo "$RESULT" | jq -r '.output.response')
    if [ -n "$RESPONSE" ] && [ "$RESPONSE" != "null" ]; then
        echo -e "${GREEN}✓ Test 1 PASSED${NC} - Got response: ${RESPONSE:0:50}..."
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}✗ Test 1 FAILED${NC} - No response in output"
        echo "$RESULT" | jq '.'
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
else
    echo -e "${RED}✗ Test 1 FAILED${NC}"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

echo ""
sleep 2

# Test 2: Longer Inference (Stress Test)
echo -e "${BLUE}[Test 2/8]${NC} Long-Form Generation (256 tokens)"
TOTAL_TESTS=$((TOTAL_TESTS + 1))

JOB_ID=$(submit_job '{
    "input": {
        "task": "inference",
        "prompt": "Write a detailed explanation of quantum computing:",
        "max_tokens": 256,
        "temperature": 0.7
    }
}')

if wait_for_job "$JOB_ID" 180; then
    RESULT=$(get_result "$JOB_ID")
    RESPONSE=$(echo "$RESULT" | jq -r '.output.response')
    WORD_COUNT=$(echo "$RESPONSE" | wc -w)

    if [ "$WORD_COUNT" -gt 50 ]; then
        echo -e "${GREEN}✓ Test 2 PASSED${NC} - Generated $WORD_COUNT words"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}✗ Test 2 FAILED${NC} - Only generated $WORD_COUNT words"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
else
    echo -e "${RED}✗ Test 2 FAILED${NC}"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

echo ""
sleep 2

# Test 3: Multiple Prompts (Batch Testing)
echo -e "${BLUE}[Test 3/8]${NC} Batch Processing (5 prompts)"
TOTAL_TESTS=$((TOTAL_TESTS + 1))

PROMPTS=(
    "What is machine learning?"
    "Explain neural networks in simple terms."
    "What are the benefits of AI?"
    "How does deep learning work?"
    "What is the future of artificial intelligence?"
)

BATCH_JOBS=()
for PROMPT in "${PROMPTS[@]}"; do
    JOB_ID=$(submit_job "{
        \"input\": {
            \"task\": \"inference\",
            \"prompt\": \"$PROMPT\",
            \"max_tokens\": 50
        }
    }")
    BATCH_JOBS+=("$JOB_ID")
    echo "  Submitted: $PROMPT"
    sleep 1
done

echo "Waiting for all jobs to complete..."
BATCH_SUCCESS=0
for JOB_ID in "${BATCH_JOBS[@]}"; do
    if wait_for_job "$JOB_ID" 120; then
        BATCH_SUCCESS=$((BATCH_SUCCESS + 1))
    fi
done

if [ "$BATCH_SUCCESS" -eq 5 ]; then
    echo -e "${GREEN}✓ Test 3 PASSED${NC} - All 5 prompts completed"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo -e "${YELLOW}⚠ Test 3 PARTIAL${NC} - $BATCH_SUCCESS/5 completed"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

echo ""
sleep 2

# Test 4: Different Temperatures
echo -e "${BLUE}[Test 4/8]${NC} Temperature Variation (0.1, 0.7, 1.0)"
TOTAL_TESTS=$((TOTAL_TESTS + 1))

TEMPS=(0.1 0.7 1.0)
TEMP_SUCCESS=0

for TEMP in "${TEMPS[@]}"; do
    JOB_ID=$(submit_job "{
        \"input\": {
            \"task\": \"inference\",
            \"prompt\": \"Tell me a creative story about AI:\",
            \"max_tokens\": 100,
            \"temperature\": $TEMP
        }
    }")

    echo "  Testing temperature: $TEMP"
    if wait_for_job "$JOB_ID" 120; then
        TEMP_SUCCESS=$((TEMP_SUCCESS + 1))
    fi
    sleep 1
done

if [ "$TEMP_SUCCESS" -eq 3 ]; then
    echo -e "${GREEN}✓ Test 4 PASSED${NC} - All temperature values worked"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo -e "${RED}✗ Test 4 FAILED${NC} - Only $TEMP_SUCCESS/3 worked"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

echo ""
sleep 2

# Test 5: Error Handling - Invalid Task
echo -e "${BLUE}[Test 5/8]${NC} Error Handling (Invalid Task)"
TOTAL_TESTS=$((TOTAL_TESTS + 1))

JOB_ID=$(submit_job '{
    "input": {
        "task": "invalid_task",
        "prompt": "test"
    }
}')

if wait_for_job "$JOB_ID" 30; then
    RESULT=$(get_result "$JOB_ID")
    ERROR=$(echo "$RESULT" | jq -r '.output.error')

    if [ -n "$ERROR" ] && [ "$ERROR" != "null" ]; then
        echo -e "${GREEN}✓ Test 5 PASSED${NC} - Correctly returned error"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}✗ Test 5 FAILED${NC} - Should have returned error"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
else
    echo -e "${RED}✗ Test 5 FAILED${NC}"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

echo ""
sleep 2

# Test 6: Performance - Latency Test
echo -e "${BLUE}[Test 6/8]${NC} Performance - Latency Test"
TOTAL_TESTS=$((TOTAL_TESTS + 1))

START_TIME=$(date +%s)
JOB_ID=$(submit_job '{
    "input": {
        "task": "inference",
        "prompt": "Quick test",
        "max_tokens": 10
    }
}')

if wait_for_job "$JOB_ID" 60; then
    END_TIME=$(date +%s)
    LATENCY=$((END_TIME - START_TIME))

    RESULT=$(get_result "$JOB_ID")
    EXEC_TIME=$(echo "$RESULT" | jq -r '.executionTime')

    echo "  Total latency: ${LATENCY}s"
    echo "  Execution time: ${EXEC_TIME}ms"

    if [ "$LATENCY" -lt 30 ]; then
        echo -e "${GREEN}✓ Test 6 PASSED${NC} - Good latency"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${YELLOW}⚠ Test 6 WARNING${NC} - Slow latency (${LATENCY}s)"
        PASSED_TESTS=$((PASSED_TESTS + 1))  # Still pass, just warn
    fi
else
    echo -e "${RED}✗ Test 6 FAILED${NC}"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

echo ""
sleep 2

# Test 7: Token Limits
echo -e "${BLUE}[Test 7/8]${NC} Token Limit Testing"
TOTAL_TESTS=$((TOTAL_TESTS + 1))

TOKEN_LIMITS=(10 50 100 200)
TOKEN_SUCCESS=0

for LIMIT in "${TOKEN_LIMITS[@]}"; do
    JOB_ID=$(submit_job "{
        \"input\": {
            \"task\": \"inference\",
            \"prompt\": \"Count from 1 to 100:\",
            \"max_tokens\": $LIMIT
        }
    }")

    echo "  Testing max_tokens: $LIMIT"
    if wait_for_job "$JOB_ID" 120; then
        TOKEN_SUCCESS=$((TOKEN_SUCCESS + 1))
    fi
    sleep 1
done

if [ "$TOKEN_SUCCESS" -eq 4 ]; then
    echo -e "${GREEN}✓ Test 7 PASSED${NC} - All token limits worked"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo -e "${RED}✗ Test 7 FAILED${NC}"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

echo ""
sleep 2

# Test 8: Rapid Fire (10 requests)
echo -e "${BLUE}[Test 8/8]${NC} Rapid Fire Test (10 concurrent requests)"
TOTAL_TESTS=$((TOTAL_TESTS + 1))

RAPID_JOBS=()
echo "Submitting 10 requests..."
for i in {1..10}; do
    JOB_ID=$(submit_job "{
        \"input\": {
            \"task\": \"inference\",
            \"prompt\": \"Request $i: Hello!\",
            \"max_tokens\": 20
        }
    }")
    RAPID_JOBS+=("$JOB_ID")
    echo -n "."
done
echo ""

echo "Waiting for completion..."
RAPID_SUCCESS=0
for JOB_ID in "${RAPID_JOBS[@]}"; do
    if wait_for_job "$JOB_ID" 180; then
        RAPID_SUCCESS=$((RAPID_SUCCESS + 1))
    fi
done

if [ "$RAPID_SUCCESS" -ge 8 ]; then
    echo -e "${GREEN}✓ Test 8 PASSED${NC} - $RAPID_SUCCESS/10 completed"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo -e "${RED}✗ Test 8 FAILED${NC} - Only $RAPID_SUCCESS/10 completed"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo -e "Total Tests: $TOTAL_TESTS"
echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
echo -e "${RED}Failed: $FAILED_TESTS${NC}"
echo ""

if [ "$FAILED_TESTS" -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    PASS_RATE=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    echo -e "${YELLOW}Pass rate: ${PASS_RATE}%${NC}"
    exit 1
fi
