class AnalysisContext:

    def __init__(self, comments, brain_context, video_context, title, memory_context=""):
        self.comments       = comments
        self.brain_context  = brain_context
        self.video_context  = video_context
        self.title          = title
        self.memory_context = memory_context
        self._results       = {}
        self._steps         = []
        self._errors        = []

    def record_step(self, step):
        self._steps.append(step)
        print(step)

    def record_error(self, agent_id, error):
        self._errors.append({'agent': agent_id, 'error': error})

    def add(self, agent_id, data):
        self._results[agent_id] = data

    def get(self, agent_id):
        return self._results.get(agent_id, {})

    def to_response(self):
        result = {}
        for data in self._results.values():
            if isinstance(data, dict):
                result.update(data)
        return result
