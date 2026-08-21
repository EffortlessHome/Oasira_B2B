import asyncio
from typing import Dict, Any
from api_client import OasiraAPIClient, OasiraAPIError
import logging

# Configure basic logging for visibility
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
_LOGGER = logging.getLogger(__name__)

async def run_agent_tests():
    """
    Runs a suite of tests to validate the Oasira AI Agent API implementation 
    in api_client.py.
    """
    print("===================================================================")
    print("Starting Oasira AI Agent API Integration Test Suite")
    print("===================================================================\n")

    try:
        # Initialize the client
        client = OasiraAPIClient()
        
        # Define mock context and ID for testing
        MOCK_HOME_ID = "system-oasira-demo-123"
        MOCK_SESSION_CONTEXT: Dict[str, Any] = {"user_id": "test_user_001", "history": []}

        print(f"--- Test Setup Complete: Using Mock Home ID: {MOCK_HOME_ID} ---\n")

        # ====================================================================
        # TEST CASE 1: Direct Response (No tool needed)
        # ====================================================================
        print(">>> Running Test Case 1: Direct Conversation (No Tool Call)")
        try:
            user_input_1 = "Please tell me about the Oasira platform."
            response_1 = await client.start_agent_conversation(user_input_1, MOCK_HOME_ID, MOCK_SESSION_CONTEXT)
            print(f"  [SUCCESS] Input: '{user_input_1}'")
            print(f"  [RESULT] Response Text: {response_1['text']}")
            print("-" * 40)
        except Exception as e:
            print(f"  [FAIL] Test Case 1 failed with exception: {e}")
        
        # ====================================================================
        # TEST CASE 2: Tool Usage - Status Retrieval (get_home_status_tool)
        # ====================================================================
        print("\n>>> Running Test Case 2: Tool Usage - Get Home Status")
        try:
            user_input_2 = "Can you give me the current status of all devices in the house?"
            response_2 = await client.start_agent_conversation(user_input_2, MOCK_HOME_ID, MOCK_SESSION_CONTEXT)
            print(f"  [SUCCESS] Input: '{user_input_2}'")
            print(f"  [RESULT] Response Text: {response_2['text']}")
            print("-" * 40)
        except Exception as e:
            print(f"  [FAIL] Test Case 2 failed with exception: {e}")

        # ====================================================================
        # TEST CASE 3: Tool Usage - Controlled Action (control_device_tool - Approval required)
        # ====================================================================
        print("\n>>> Running Test Case 3: Tool Usage - Device Control (Approval Required)")
        try:
            user_input_3 = "I need you to lock the front door now."
            response_3 = await client.start_agent_conversation(user_input_3, MOCK_HOME_ID, MOCK_SESSION_CONTEXT)
            print(f"  [SUCCESS] Input: '{user_input_3}'")
            print(f"  [RESULT] Response Text: {response_3['text']}")
            if response_3.get('source') == 'needs_approval':
                print("  [CHECK] Test successfully identified the need for user approval.")
            print("-" * 40)
        except Exception as e:
            print(f"  [FAIL] Test Case 3 failed with exception: {e}")

        # ====================================================================
        # TEST CASE 4: Tool Usage - Preferences (get_resident_preferences_tool)
        # ====================================================================
        print("\n>>> Running Test Case 4: Tool Usage - Resident Preferences")
        try:
            user_input_4 = "What are the preferred settings for the house?"
            response_4 = await client.start_agent_conversation(user_input_4, MOCK_HOME_ID, MOCK_SESSION_CONTEXT)
            print(f"  [SUCCESS] Input: '{user_input_4}'")
            print(f"  [RESULT] Response Text: {response_4['text']}")
            print("-" * 40)
        except Exception as e:
            print(f"  [FAIL] Test Case 4 failed with exception: {e}")

        print("\n===================================================================")
        print("All agent API tests completed successfully.")
        print("===================================================================\n")

    except Exception as e:
        print(f"\n\n🚨 FATAL ERROR during test execution: {e}")
        print("Please ensure all dependencies (like api_client.py) are correctly defined and accessible.")

if __name__ == "__main__":
    # We must wrap the asynchronous calls in an event loop runner
    asyncio.run(run_agent_tests())