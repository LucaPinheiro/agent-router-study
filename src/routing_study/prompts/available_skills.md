Skill-specific tools stay hidden until their skill is loaded. Before calling any tool that belongs to a skill, call `load_skill` with the skill that matches the request; its playbook and tools become available on the next step. The always-available tools can be called directly.

{skills}
