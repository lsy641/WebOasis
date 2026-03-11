from abc import ABC
from weboasis.ui_manager.playwright_manager import SyncPlaywrightManager
from weboasis.ui_manager.selenium_manager import SyncSeleniumManager
from weboasis.agents.base import WebAgent, RoleAgent, Message_Center
from weboasis.agents.types import Observation
from weboasis.act_book import ActBookController
from datetime import datetime
from typing import Callable
import base64
import os
import logging
logger = logging.getLogger(__name__)

class DualAgent:  
    
    def __init__(self, client, model, act_book: ActBookController, web_manager="playwright", test_id_attribute: str = "data-testid", log_dir: str = None, hard_coded_goal: Callable[[int], str] = None, verbose: bool = True, max_message_history: int = 50, extra_http_headers: dict = None, proxy: dict = None, user_agent: str = None):
        """
        Initialize the DualAgent.
        
        Args:
            client: OpenAI client instance
            model: Model name to use
            act_book: ActBookController instance
            web_manager: Web manager type ("playwright" or "selenium")
            test_id_attribute: Attribute name for test IDs
            log_dir: Directory for logs
            hard_coded_goal: Function that returns goals for hard-coded steps
            verbose: Whether to print verbose output
            max_message_history: Maximum number of messages to keep in history
            extra_http_headers: Dictionary of additional HTTP headers (only for playwright)
            proxy: Proxy configuration dict with 'server' key (only for playwright)
            user_agent: Custom user agent string (only for playwright)
        """
        # Create the appropriate web manager based on the parameter
        if web_manager == "playwright":
            self._web_manager = SyncPlaywrightManager(
                test_id_attribute=test_id_attribute,
                extra_http_headers=extra_http_headers,
                proxy=proxy,
                user_agent=user_agent
            )
        elif web_manager == "selenium":
            self._web_manager = SyncSeleniumManager(test_id_attribute=test_id_attribute)
        else:
            # Default to playwright
            self._web_manager = SyncPlaywrightManager(
                test_id_attribute=test_id_attribute,
                extra_http_headers=extra_http_headers,
                proxy=proxy,
                user_agent=user_agent
            )
        
        self._vlm_client = client
        
        self._model = model
        
        self.role_agent = RoleAgent(name="role_agent", verbose=verbose)
        self.web_agent = WebAgent(name="web_agent", verbose=verbose)
        # a message center to store the messages for multi-agent communication
        self.message_center = Message_Center(max_history=max_message_history)
        # an act book to store the actions for the web agent to execute
        self.act_book = act_book
        # a function to generate the goal for the web agent to execute
        self.hard_coded_goal = hard_coded_goal
        
        self._step_idx = 0
        # verbose for the web agent and role agent
        self.verbose = verbose
        
        if log_dir is None:
            self.log_dir = "./logs/"
        else:
            self.log_dir = log_dir
        
    @property
    def web_manager(self):
        return self._web_manager 
    
    @property
    def client(self):
        return self._vlm_client  
    
    @property
    def model(self):
        return self._model
    
    
    @property
    def step_idx(self):
        return self._step_idx
    
    @step_idx.setter
    def step_idx(self, value: int):
        self._step_idx = value
    
    
    def step(self):
        
        # 0. if the step is less than the hard-coded goal, use the hard-coded goal
        
        if self.hard_coded_goal is not None and self.hard_coded_goal(self.step_idx):
            # 1. web agent get observation from the web manager
            web_agent_observation = self.web_agent.observe(self.web_manager)
            self.save_observation_log(web_agent_observation)
            # 2. web agent get hard coded goal
            goal = self.hard_coded_goal(self.step_idx)
            self.save_web_action_log(goal, "role_agent")
            # 3. web agent act based on the goal
            web_agent_action = self.web_agent.act(self.web_manager, self.act_book, self.client, self.model, web_agent_observation, goal, self.message_center)
            self.save_web_action_log(f"{web_agent_action['raw_response']} \n  {web_agent_action['operation']}({str(web_agent_action['parameters'])}) \n success: {str(web_agent_action['success'])}", "web_agent")
            # 4. update the step
            self.step_idx += 1
            self.role_agent.step_idx += 1
            self.web_agent.step_idx += 1           
            return

        else:

            # 1. web agent get observation from the web manager
            web_agent_observation = self.web_agent.observe(self.web_manager)
            self.save_observation_log(web_agent_observation)
            
            # 2. role agent get observation from  the information given by the web agent, but it could be enhanced by other information sources.
            role_agent_observation = self.role_agent.observe(web_agent_observation)
            self.save_observation_log(role_agent_observation)
            
            # 3. role agent decide the goal for the web agent
            goal = self.role_agent.act(self.client, self.model, role_agent_observation, self.message_center)
            self.save_web_action_log(goal, "role_agent")
            
            # 4. web agent act based on the goal
            web_agent_action = self.web_agent.act(self.web_manager, self.act_book, self.client, self.model, web_agent_observation, goal, self.message_center)
            # Use executed_text if available, otherwise fall back to detailed format
            log_text = web_agent_action.get('executed_text') or f"{web_agent_action['raw_response']} \n  {web_agent_action['operation']}({str(web_agent_action['parameters'])}) \n success: {str(web_agent_action['success'])}"
            self.save_web_action_log(log_text, "web_agent")
            logger.debug(f"web_agent_action: {log_text}")
            # 5. update the step
            self._step_idx += 1
            self.role_agent.step_idx += 1
            self.web_agent.step_idx += 1
            return
    
    def reset(self):
        self.step = 0
        self.role_agent.reset()
        self.web_agent.reset()


            
    def save_web_action_log(self, action_log: str, name: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.log_dir is None:
            self.log_dir = "./logs/"
            logger.info(f"log_dir not set, using default: {self.log_dir}")
            os.makedirs(self.log_dir, exist_ok=True)
        web_log_file = os.path.join(self.log_dir, f"agent_log.txt")  
        with open(web_log_file, "a") as f:
            f.write(f"== [{timestamp}] {name} action step {self.step_idx} ==")
            f.write(f"{action_log}")
            f.write(f"== end of action log ==\n")
            
        
        
    def save_observation_log(self, observation: Observation):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.log_dir is None:
            self.log_dir = "./logs/"
            logger.info(f"log_dir not set, using default: {self.log_dir}")
        os.makedirs(self.log_dir, exist_ok=True)
        web_log_file = os.path.join(self.log_dir, f"agent_log.txt") 
        # only save the image every 50 steps
        web_image_file = os.path.join(self.log_dir, f"web_agent_image_{self.step_idx%50}.png")
        if self.step_idx == 0 and os.path.exists(web_log_file):
            os.remove(web_log_file)
        if self.step_idx == 0 and os.path.exists(web_image_file):
            os.remove(web_image_file)
        with open(web_image_file, "wb") as f:
            f.write(base64.b64decode(observation.image))
        with open(web_log_file, "a") as f:
            # timestamp, step, source, text, image, metadata
            f.write(f"== [{timestamp}] {observation.source} observations, step {self.step_idx} ==")
            f.write(f"text observation: {observation.text}\n")
            f.write(f"image observation: check file at {web_image_file}\n")
            f.write(
                f"metadata observation: "
                f"{ {k: v for k, v in observation.metadata.items() if k != 'accessibility_tree'} }\n"
            )
            f.write(f"== end of observation ==\n")