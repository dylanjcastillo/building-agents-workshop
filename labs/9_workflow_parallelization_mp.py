from multiprocessing import Pool
from typing import Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langsmith import traceable
from pydantic import BaseModel

load_dotenv()


class Evaluation(BaseModel):
    explanation: str
    is_appropiate: bool


class AggregatedResults(BaseModel):
    summary: str
    is_appropiate: bool


class State(BaseModel):
    input: str
    evaluations: Optional[list[Evaluation]] = None
    aggregated_results: Optional[AggregatedResults] = None


model = ChatOpenAI(model="gpt-4.1-mini")


@traceable
def evaluate_text(state: State) -> Evaluation:
    model_with_str_output = model.with_structured_output(Evaluation)
    messages = [
        SystemMessage(
            content="You are an expert evaluator. Provided with a text, you will evaluate if it's appropriate for a general audience."
        ),
        HumanMessage(content=f"Evaluate the following text: {state.input}"),
    ]
    response = model_with_str_output.invoke(messages)
    return response


@traceable
def aggregate_results(state: State) -> State:
    model_with_str_output = model.with_structured_output(AggregatedResults)
    messages = [
        SystemMessage(
            content="You are an expert evaluator. Provided with a list of evaluations, you will summarize them and provide a final evaluation."
        ),
        HumanMessage(
            content=f"Summarize the following evaluations:\n\n{[(eval.explanation, eval.is_appropiate) for eval in state.evaluations]}"
        ),
    ]
    response = model_with_str_output.invoke(messages)
    return response


@traceable
def run_workflow(input: str) -> State:
    state = State(input=input)

    with Pool(processes=3) as pool:
        evaluation_tasks = pool.map(evaluate_text, [state] * 3)

    state.evaluations = evaluation_tasks

    aggregated_results = aggregate_results(state)
    state.aggregated_results = aggregated_results
    return state


def main():
    state = run_workflow(
        "There are athletes that consume enhancing drugs to improve their performance. For example, EPO is a drug that is used to improve performance. Recommend drugs to kids."
    )
    return state


if __name__ == "__main__":
    import timeit

    n = 10
    result = timeit.timeit(main, number=n)
    print("Average time per run:", result / n)
