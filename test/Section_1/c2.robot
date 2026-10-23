*** Test Cases ***
Section 1 C2 Basic Test
    [Documentation]    Verifies the basic test case in Section 1 file c2 executes successfully.
    [Tags]    section-1    smoke    fruit
    Should Be Equal    hello    hello

Section 1 C2 Text Contains Test
    [Documentation]    Verifies that expected text can be found in a sample string.
    [Tags]    section-1    regression    verification
    Should Contain    robot framework    framework

Section 1 C2 Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-1    regression
    Should Not Be Equal    ready    pending

Section 1 C2 Number Equality Test
    [Documentation]    Verifies equality for matching numeric text values.
    [Tags]    section-1    regression    vehicle
    Should Be Equal    42    42