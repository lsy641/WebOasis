from abc import ABC, abstractmethod    
from weboasis.ui_manager.base_manager import SyncWEBManager
from weboasis.agents.types import Observation, Message
import logging
import time
import base64
from typing import List
from weboasis.utils import messages_to_list
import os
import string
import copy
from weboasis.act_book import ActBookController
from weboasis.agents.constants import WEBAGENT_OBSERVE_PROMPT, WEBAGENT_EXAMPLE_PROFILE, WEBAGENT_ACT_PROMPT, WEBAGENT_INTENTION_PARSE_PROMPT
from weboasis.utils import interactive_elems_to_str, messages_to_list, messages_to_str_without_image
from datetime import datetime
import json

logger = logging.getLogger(__name__)




    
class BaseAgent(ABC):
    """Base class for all agents in the system"""
    
    def __init__(self, name: str, log_dir: str = None):
        self._name = name
        if log_dir is None:
            self._log_dir = f"./logs/{name}/"
        else:
            self._log_dir = log_dir
        self._step_idx = 0
        self._memory = []
        os.makedirs(self._log_dir, exist_ok=True)
    
    @abstractmethod
    def observe(self, *args, **kwargs):
        """Observe the environment and return observations"""
        pass
    
    @abstractmethod
    def act(self, *args, **kwargs):
        """Take action based on observations and memory"""
        pass
      
    @property
    def name(self):
        return self._name
    
    @property
    def step_idx(self):
        return self._step_idx
    
    @property
    def log_dir(self):
        return self._log_dir
    
    def reset(self):
        """reset the step counter"""
        self._step_idx = 0
        
    @ step_idx.setter
    def step_idx(self, value: int):
        self._step_idx = value
        



class Message_Center:
    """Message controller for agents"""
    
    def __init__(self, max_history: int = 50):
        """
        Initialize the message center.
        
        Args:
            max_history: Maximum number of messages to keep in history (default: 50)
        """
        self.messages: List[Message] = []
        self.max_history = max_history
    
    def add_message(self, message: Message):
        return self.messages.append(message)
        
    def get_messages(self):
        # only return the deep copy of the messages
        # return the last max_history messages
        return copy.deepcopy(self.messages)[-self.max_history:]
    
    def add_system_message(self, first_message: Message = None, last_message: Message = None):
        # Because the system message depends on the role, we only allow real-time construction and don't allow any system message actually stored in the message center.
        # The system message can be either added to the first or the last of the messages.
        messages = self.get_messages()
        if first_message is not None:
            messages.insert(0, first_message)
        if last_message is not None:
            messages.append(last_message)
        return messages
    
    def get_messages_str(self):
        messages_str = ""
        for message in self.messages:
            # message.content is a list of dicts
            # if content has image, we should not print it
            for content in message.content:
                if "image_url" == content["type"]:
                    messages_str += f"{message.name}: [image]\n"
                else:
                    messages_str += f"{message.name}: {content[content['type']]}\n"
        return messages_str
    
    
class WebAgent(BaseAgent):
    def __init__(self, name: str, log_dir: str = None, verbose: bool = True):
        super().__init__(name, log_dir)
        self.verbose = verbose
        
    def observe(self, web_manager: SyncWEBManager): 
        web_manager.hide_developer_elements()
        
        # 0. Check for reCAPTCHA and pause if detected
        if hasattr(web_manager, 'pause_for_recaptcha'):
            web_manager.pause_for_recaptcha()
        
        # 1. Mark elements
        count = web_manager.mark_elements()
        
        # 2. Extract accessibility tree
        accessibility_tree = web_manager.get_accessibility_tree(max_depth=10)
        
        # logger.debug(f"accessibility_tree: {accessibility_tree}")
        
        if count == 0:
            logger.error(
                "Still no elements marked after retry. This may indicate a page loading issue."
            )
            
        # 3. Identify interactive elements
        interactive_elements = web_manager.identify_interactive_elements(max_retries=2) 
        web_manager.outline_interactive_elements(interactive_elements, max_retries=2, retry_delay=1000)
        
        # 4. Take screenshot
        screenshot = web_manager.screenshot(path=None)
        
        
        base64_image = base64.b64encode(screenshot).decode('utf-8')
        
        # 5. Flatten interactive elements to string
        interactive_elements_str = interactive_elems_to_str(interactive_elements)
        
        # 6. Create observation
        observation = Observation(image=base64_image, text="", metadata={"interactive_elements":interactive_elements_str, "accessibility_tree":accessibility_tree}, timestamp=time.time(), source="web_agent")
        web_manager.show_developer_elements()
        
 
        return observation
    
    def act(self, web_manager: SyncWEBManager, act_book: ActBookController, client, model, observation: Observation, goal: str, message_center: Message_Center):   
        
        if self.verbose:
            web_manager.show_decision_making_process(goal) 
        
        # 1. get the interactive elements and the screenshot from the observation
        interactive_elements_str = observation.metadata["interactive_elements"]
        logger.debug(f"interactive_elements: {interactive_elements_str}")
        base64_image = observation.image
        
        logger.info(f"user output: {goal}")
        
        # 2. get the action space description from the act book
        action_space_desc = act_book.get_action_space_description(preferred_method="test_id")
        # logger.debug(f"action_space_desc: {action_space_desc}")
        
        # logger.debug(f"action_space_desc: {action_space_desc}")
        
        # 2.1 get the accessibility tree
        accessibility_tree = observation.metadata["accessibility_tree"]
        
        # 3. prepare the message for the web agent to generate the web action           
        prompt = string.Template(WEBAGENT_ACT_PROMPT).safe_substitute({
            "interactive_elements_str": interactive_elements_str,
            "action_space_desc": action_space_desc,
            "accessibility_tree": accessibility_tree,
            "goal": goal
            })        
           
        system_message = Message(name="system", 
                content=[
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": "high"
                    }
                    }
                ], time=time.time())
        messages = message_center.add_system_message(last_message=system_message)
        messages = messages_to_list(messages, mode="openai", name="web_agent")
        
        # remove content of the image_url to print
        # logger.debug(f"messages: {json.dumps(messages_to_str_without_image(messages), indent=1)}")
        
        
        # 4. send the messages to client to generate the web action

        response = client.chat.completions.create(model=model, messages=messages)
        response = response.choices[0].message.content
        
        logger.debug(f"response: {response}")
        
        
        # Get available operations for parsing
        available_operations = act_book.list_operations()
        
        # 5. parse the response to get the action
        parsed_action = web_manager.parser.parse(response, available_operations)
        logger.debug(f"Parsed action: {parsed_action}")
        
        # 6. execute the action if the action is parsed successfully
        if parsed_action:

            result = act_book.execute_operation(parsed_action.operation_name, web_manager, **parsed_action.parameters)
            
            
            if not result.success:
                logger.error(f"Action execution failed: {result.error}")
                
            
            try:
                web_manager.remove_outline_elements()
            except Exception as e:
                logger.error(f"Error in removing outline elements: {e}")
            
            # Build status suffix with error information
            status = "success" if result.success else "failed"
            status_suffix = f" (status: {status}"
            if result.error:
                status_suffix += f", error: {result.error}"
            status_suffix += ")"
            
            executed_text = f"The executed action is: {response}{status_suffix}"
            message_center.add_message(Message(name="web_agent", content=[{"type": "text", "text": executed_text}], time=time.time()))          
            return {
                        'operation': parsed_action.operation_name,
                        'parameters': parsed_action.parameters,
                        'raw_response': response,
                        'confidence': parsed_action.confidence,
                        'parser': parsed_action.parser_type,
                        'success': result.success,
                        'error': result.error,
                        'executed_text': executed_text
                    }
        else:
            logger.error(f"Failed to parse action: {response}")
            executed_text = f"Failed to parse action: {response} (status: failed, error: parsing failed)"
            message_center.add_message(Message(name="web_agent", content=[{"type": "text", "text": executed_text}], time=time.time()))
            
            return {
                'raw_response': response,
                'success': False,
                'operation': None,
                'parameters': None,
                'confidence': None,
                'parser': None,
                'error': 'parsing failed',
                'executed_text': executed_text
            }


            
           


   
                 
    
    
class RoleAgent(BaseAgent):
    
    def __init__(self, name: str, log_dir: str = None, verbose: bool = True):
        super().__init__(name, log_dir)
        self.verbose = verbose
        
        
    def observe(self, observe_message: Message):      
        # we can add more observation elements. But for now, we just pass the observation message from the web agent to the role agent.     
        return observe_message
        
    
    def act(self, client, model, observation: Observation, message_center: Message_Center):       
        
        # 1. get the interactive elements and the screenshot from the observation
        interactive_elements_str = observation.metadata["interactive_elements"]
        base64_image = observation.image 
        # 2. prepare the prompt for the role agent to generate the goal and other information for the web agent
        prompt = string.Template(WEBAGENT_OBSERVE_PROMPT).safe_substitute(
                {"interactive_elements_str": interactive_elements_str}
        )  
                           
        # 3. assemble the prompt and observation into a message for role agent to act
        ob2act_message = Message(name="system", 
                content=[
                {"type": "text", "text": prompt},
                    {"type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": "high"}
                    }
                ], time=time.time())
        # 4. construct the profile message for the role agent
        profile_message_for_roleagent = Message(name="system", content=[{"type": "text", "text": WEBAGENT_EXAMPLE_PROFILE}], time=time.time())
        
        # 5. add the profile message as the first system message of all, and add the ob2act message as the latest system message.
        messages = message_center.add_system_message(first_message=profile_message_for_roleagent, last_message=ob2act_message)
        
        
        
        
        
        # 7. convert the messages to the list of messages for the openai client
        messages = messages_to_list(messages, mode="openai", name="role_agent")

        # logger.info(f"messages: {json.dumps(messages_to_str_without_image(messages), indent=1)}")


        try:
            response = client.chat.completions.create(model=model, messages=messages)
            response = response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error in role agent act: {e}")
            response = "Error in role agent act"
        
        message_center.add_message(Message(name="role_agent", content=[{"type": "text", "text": response}], time=time.time()))
        
        return response
        
        

    
    


