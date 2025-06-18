import asyncio
from typing import Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langsmith import traceable
from pydantic import BaseModel

load_dotenv()


class Evaluation(BaseModel):
    is_appropiate: bool
    explanation: str


class AggregatedResults(BaseModel):
    is_appropiate: bool
    summary: str


class State(BaseModel):
    input: str
    evaluations: Optional[list[Evaluation]] = None
    aggregated_results: Optional[AggregatedResults] = None


model = ChatOpenAI(model="gpt-4.1-mini")


@traceable
async def evaluate_text(state: State) -> Evaluation:
    model_with_str_output = model.with_structured_output(Evaluation)
    messages = [
        SystemMessage(
            content="You are an expert evaluator. Provided with a text, you will evaluate if it's appropriate for a general audience."
        ),
        HumanMessage(content=f"Evaluate the following text: {state.input}"),
    ]
    response = await model_with_str_output.ainvoke(messages)
    return response


@traceable
async def aggregate_results(state: State) -> State:
    model_with_str_output = model.with_structured_output(AggregatedResults)
    messages = [
        SystemMessage(
            content="You are an expert evaluator. Provided with a list of evaluations, you will summarize them and provide a final evaluation."
        ),
        HumanMessage(
            content=f"Summarize the following evaluations:\n\n{[(eval.explanation, eval.is_appropiate) for eval in state.evaluations]}"
        ),
    ]
    response = await model_with_str_output.ainvoke(messages)
    return response


@traceable
async def run_workflow(input: str) -> State:
    state = State(input=input)

    evaluation_tasks = [evaluate_text(state) for _ in range(3)]
    state.evaluations = await asyncio.gather(*evaluation_tasks)

    aggregated_results = await aggregate_results(state)
    state.aggregated_results = aggregated_results
    return state


def main():
    state = asyncio.run(
        run_workflow(
            "There are athletes that consume enhancing drugs to improve their performance. For example, EPO is a drug that is used to improve performance."
        )
    )
    return state


if __name__ == "__main__":
    import timeit

    n = 10
    result = timeit.timeit(main, number=n)
    print(result / n)
