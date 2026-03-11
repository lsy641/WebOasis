<div align="center">
<img src="docs/img/log3.png" alt="WebOasis Logo" >

Handling "Any site. Any page. Any UI. Any complexity" for your web tasks.

[![GitHub](https://img.shields.io/badge/GitHub-WebOasis-181717?logo=github)](https://github.com/lsy641/WebOasis)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/lsy641/WebOasis/blob/main/LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17052503.svg)](https://doi.org/10.5281/zenodo.17052503)
[![GitHub stars](https://img.shields.io/github/stars/lsy641/WebOasis?style=social)](https://github.com/lsy641/WebOasis/stargazers)
</div>





<p align="center">
  <a href="https://lsy641.github.io/WebOasis/demo_video.html">
    <img src="https://img.youtube.com/vi/UgjgfZAmVJ0/maxresdefault.jpg" alt="Watch the video" style="max-width:100%;height:auto;display:block;">
  </a>
</p>



WebOasis is a framework for building AI-driven web agents on real, complex websites. 

## Updates

<div style="max-height: 100px; overflow-y: auto; padding: 8px 0;">

- **Proxy, user-agent, headers**: New parameters for custom proxy, user-agent, and request headers in both Playwright and Selenium managers
- **reCAPTCHA**: Detection and handling for reCAPTCHA challenges
- **Safe close**: Improved resource cleanup on browser/manager shutdown
- **Interactive class patterns**: Configurable patterns for identifying interactive elements
- **frame_mark_elements.js**: Page stability checks, chat-interface handling, and DOM element marking
- **identify_interactive_elements.js**: Expanded interactive element detection
- **Max history messages**: Configurable limit on conversation history
- **Execution outcomes**: Richer execution feedback in agent messages
- **Accessibility tree**: Accessibility information included in agent observations
- **Registry updates**: Improved operation registration flow
- **Demo**: Example of adding custom operations
- **Lowercase operations**: Case-insensitive operation extraction in the parser

</div>

## Features
- **Any site. Any page. Any UI. Any complexity.** 
Robust handling of dynamic, highly interactive pages. You focus on research—no brittle low‑level UI hacking. If you run into a tricky page the agent can't yet handle, please open a [request](https://github.com/lsy641/WebOasis/issues/new) and we'll help.

- **One-parameter engine switch (Playwright ↔ Selenium).** 
Choose your UI engine per experiment without changing operation code or test-suite boilerplate.

- **Dual-agent architecture for clarity and power.** 
Role Agent (human-like intent, high-level reasoning) + Web Agent (browser expert, low-level actions). Clean separation of observation and control.

- **Supports both task automatiton and interactive (tutor‑style) agents (TODO).** 
For tutor-style agents, Human (novice) → Role Agent (proficient user) → Web Agent (operator): guide, involve, and supervise actions in the loop.

## Installation

- From source (Recommended):
```bash
git clone https://github.com/lsy641/WebOasis.git
cd WebOasis
pip install -e .
```

- PyPI:
```bash
pip install weboasis
```

## Configuration

WebOasis uses prompt-based configuration for its AI agents. You can customize these prompts by setting the `WEBOASIS_PROMPTS_PATH` environment variable to point to your own `prompts.yaml` file.

### Customizing Prompts

```bash
# Set the path to your custom prompts file
export WEBOASIS_PROMPTS_PATH="/path/to/your/custom/prompts.yaml"

# Run your script
python your_script.py
```

### Prompts File Format

Your custom `prompts.yaml` should follow the same structure as the default:

```yaml
observe_prompt: |-
  # Interactive Elements
  ${interactive_elements_str}
  
  # Your custom instructions here
  - Be more cautious when interacting with elements
  - Focus on accessibility-first interactions
  
  # Response Format
  [Action] (Your custom format)

act_prompt: |-
  # Interactive elements:
  ${interactive_elements_str}
  
  # Action Space
  ${action_space_desc}
  
  # Your custom instructions here
  
  # Goal:
  ${goal}
  
  # Response Format


example_profile: |-
  # Your custom user profile
  You are a [describe your persona]
  
  ## Task Description
  [describe what you want to accomplish]
  
  ## Profile
  [describe your characteristics and preferences]
```

### Available Variables

The following variables can be used in your prompts:
- `${interactive_elements_str}` - List of interactive elements on the page
- `${action_space_desc}` - Available actions the agent can perform
- `${accessibility_tree}` - Page accessibility information
- `${goal}` - Current goal/task to accomplish

## Run a demo

The demo simulates a prostate cancer patient using a newly developed visit‑prep web app to surface UI design and system usability issues. At each step, the DualAgent observes page dynamics, articulates the user experience, infers intent, and executes the next UI action.

```bash
python WebOasis/scripts/demo.py
```

Demo core logic (simplified):
```python
import os
from openai import OpenAI
from weboasis.act_book import ActBookController
from weboasis.agents import DualAgent
from weboasis.agents.constants import TEST_ID_ATTRIBUTE

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
act_book = ActBookController(auto_register=False)
act_book.register("browser/interaction")
act_book.register("browser/navigation")
act_book.register("general/flow")

agent = DualAgent(
    client=client, model="gpt-4.1-mini",
    act_book=act_book, web_manager="playwright",
    test_id_attribute=TEST_ID_ATTRIBUTE, log_dir="./logs/demo", verbose=True,
)

for _ in range(20):
    if not agent.web_manager.is_browser_available():
        break
    agent.step()
```

## Project structure

```
WebOasis/
├── act_book/                      # Operations and registry
│   ├── core/                      # Base classes, registry, automator interface
│   ├── book/
│   │   ├── browser/
│   │   │   ├── interaction.py     # Click/Type/Scroll/... operations
│   │   │   ├── navigation.py      # Navigate/Back/Forward/Tab ops
│   │   │   └── extraction.py      # GetText/Attribute/Screenshot/Title/URL
│   │   ├── dom/selector.py        # Find/Wait/Exists/Visible
│   │   ├── composite/
│   │   │   ├── forms.py           # FillForm/Login/SubmitForm
│   │   │   └── highlighting.py    # Visual highlight helpers
│   │   └── general/flow.py        # NoAction (wait)
│   └── engines/
│       ├── playwright/playwright_automator.py
│       └── selenium/selenium_automator.py
├── ui_manager/                    # Browser managers and parser
│   ├── base_manager.py
│   ├── playwright_manager.py
│   ├── selenium_manager.py
│   ├── parsers/simple_parser.py   # Robust function-call parser
│   ├── js_adapters.py             # Selenium JS adapters (sync/async)
│   └── constants.py               # Loads injected JS utilities
├── agents/                        # Agents and shared types
│   ├── base.py                    # BaseAgent, WebAgent, RoleAgent
│   ├── dual_agent.py              # Orchestrates Role + Web agents
│   ├── constants.py               # Prompts and shared config
│   └── types.py                   # Observation/Message/etc.
├── javascript/                    # Injected browser-side utilities
│   ├── frame_mark_elements.js
│   ├── add_outline_elements.js
│   ├── identify_interactive_elements.js
│   ├── extract_accessbility_tree.js
│   ├── create_developper_panel.js
│   ├── hide_developer_elements.js
│   └── show_developer_elements.js
├── config/prompts.yaml            # Act/observe prompts
└── scripts/demo.py                # Minimal runnable example
```



## Citation

If you use WebOasis in your research, please cite:

```bibtex
@software{siyang_liu_2025_17052503,
  author       = {Siyang Liu},
  title        = {lsy641/WebOasis: 0.1.5},
  month        = sep,
  year         = 2025,
  publisher    = {Zenodo},
  version      = {0.1.5},
  doi          = {10.5281/zenodo.17052503},
  url          = {https://doi.org/10.5281/zenodo.17052503},
  swhid        = {swh:1:dir:3e01a9805d7e6f1f92703629987b90fbc07a3218;origin=https://doi.org/10.5281/zenodo.17052502;visit=swh:1:snp:5d80fd402b00b67f790a56c6532a88a6e9300f88;anchor=swh:1:rel:d8fbac11afe389ce44a306513eefc372905d900b;path=lsy641-WebOasis-3bec1d9},
}
```

## License

Apache License 2.0. See the `LICENSE` file.

