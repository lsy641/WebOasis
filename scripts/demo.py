import logging
from weboasis.act_book import ActBookController
from weboasis.agents import DualAgent
from weboasis.agents.constants import TEST_ID_ATTRIBUTE
from openai import OpenAI
import os

logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )

# Suppress OpenAI debug logs while keeping our debug logs
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Create controller for operation management
act_book = ActBookController(auto_register=False, log_level="DEBUG")

# Get only the operations we want from the list
# get_operation_classes_by_names() uses auto-register to temporarily make all operations available
desired_operations = ['noaction', 'click', 'doubleclick', 'hover', 'formfill', 'type', 'clearinput', 'check', 'uncheck', 'selectoption', 'scroll', 'press', 'mouseclick', 'mousemove', 'keyboardtype', 'keyboardpress', 'draganddrop', 'uploadfile', 'playvideo', 'pausevideo', 'navigate', 'back', 'forward', 'refresh', 'waitfornavigation', 'newtab', 'closetab', 'focustab']
operations = act_book.get_operation_classes_by_names(desired_operations)

# Register only the selected operations
act_book.register(list(operations.values()))

# Verify only the selected operations are registered
operations_list = act_book.list_operations()
print(f"Registered operations: {operations_list}")
print(f"Total registered operations: {len(operations_list)}")

# Get operations summary
summary = act_book.get_operations_summary()
logger.info(f"Operations summary: {summary}")


   
# Initialize the openai client and the model
api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=api_key, base_url="https://api.openai.com/v1")
model = "gpt-4.1-mini"


'''
Usually, the first sevral steps are hard-coded, such as go to the target page, login, etc. You can hard-code the goals for the first several steps.
Hard-coded goals for the first several steps, separated by [STEP]
For example, "[STEP]go to https://... [STEP]type password 1234 if requiring login[STEP]click submit button"
'''
def build_hard_coded_goal(step_goals_text: str):
    # Split and strip, ignore empty
    goals = [g.strip() for g in step_goals_text.split('[STEP]') if g.strip()]
    logger.info(f"intial goals: {goals}")
    def hard_coded_goal(step_idx):
        if 0 <= step_idx < len(goals):
            return goals[step_idx]
        return ""
    return hard_coded_goal

hard_coded_goal = build_hard_coded_goal("[STEP]go to https://cancervisitprep.webanonymous75.win/[STEP] wait 2 seconds for the page to be stable[STEP] collapse the left side bar for guidelines 'what you should know before you start'[STEP] scroll down to the bottom of the page")

# Run the dual agent to test the web application, set verbose to True to visualize the decision making process
dual_agent = None
try:
    dual_agent = DualAgent(client=openai_client, model=model, act_book=act_book, web_manager="palywright", test_id_attribute=TEST_ID_ATTRIBUTE, log_dir="./logs/demo", hard_coded_goal=hard_coded_goal, verbose=True)
    # allow the user to pause the execution for debugging
    dual_agent.web_manager.pause_for_debug()
    iterations = 300

    for i in range(iterations):
        if not dual_agent.web_manager.is_browser_available():
            logger.error(f"Browser is not available, exiting...")
            break
        dual_agent.step()
        # detect if the user wants to pause the execution for debugging
        dual_agent.web_manager.pause_for_debug()
finally:
    # Properly close the browser/playwright engine
    try:
        if dual_agent and dual_agent.web_manager:
            dual_agent.web_manager.close()
    except Exception as e:
        logger.error(f"Error closing web manager: {e}")
    
    





