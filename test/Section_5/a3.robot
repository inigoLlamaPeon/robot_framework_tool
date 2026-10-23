*** Test Cases ***
Section 5 A3 Basic Test
    [Documentation]    Verifies the basic test case in Section 5 file a3 executes successfully.
    [Tags]    section-5    smoke
    Should Be Equal    hello    hello

Section 5 A3 Text Contains Test
    [Documentation]    Verifies that expected text can be found in a sample string.
    [Tags]    section-5    regression
    Should Contain    completed task    task

Section 5 A3 Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-5    regression
    Should Not Be Equal    low    high

Section 5 A3 Number Equality Test
    [Documentation]    Verifies equality for matching numeric text values.
    [Tags]    section-5    regression
    Should Be Equal    11    11