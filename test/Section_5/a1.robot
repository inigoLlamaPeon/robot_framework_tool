*** Test Cases ***
Section 5 A1 Basic Test
    [Documentation]    Verifies the basic test case in Section 5 file a1 executes successfully.
    [Tags]    section-5    smoke
    Should Be Equal    hello    hello

Section 5 A1 Text Contains Test
    [Documentation]    Verifies that expected text can be found in a sample string.
    [Tags]    section-5    regression
    Should Contain    final verification    verification

Section 5 A1 Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-5    regression
    Should Not Be Equal    accepted    rejected

Section 5 A1 Exact Text Test
    [Documentation]    Verifies equality for matching sample text values.
    [Tags]    section-5    regression
    Should Be Equal    finished    finished

Section 5 A1 Number Equality Test
    [Documentation]    Verifies equality for matching numeric text values.
    [Tags]    section-5    regression
    Should Be Equal    5    5

Section 5 Command Line Variables Test
    [Documentation]    Verifies user-defined variables can be supplied to the Robot Framework run.
    [Tags]    section-5    variables
    Log    ENV=${ENV}
    Log    USER=${USER}
    Log    TIMEOUT=${TIMEOUT}
    Log    ${CLI_TEXT}
    Log Many    @{CLI_LIST}
    Log    ${CLI_SET}
    Log    ${CLI_TUPLE}
    Log    ${CLI_DICTIONARY}