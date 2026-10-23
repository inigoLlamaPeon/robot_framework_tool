*** Test Cases ***
Section 4 A3 Basic Test
    [Documentation]    Verifies the basic test case in Section 4 file a3 executes successfully.
    [Tags]    section-4    smoke
    Should Be Equal    hello    hello

Section 4 A3 Text Contains Test
    [Documentation]    Verifies that expected text can be found in a sample string.
    [Tags]    section-4    regression
    Should Contain    framework keyword    keyword

Section 4 A3 Different Values Test
    [Documentation]    Verifies that two distinct sample values are not equal.
    [Tags]    section-4    regression
    Should Not Be Equal    connected    disconnected

Section 4 A3 Exact Text Test
    [Documentation]    Verifies equality for matching sample text values.
    [Tags]    section-4    regression
    Should Be Equal    case passed    case passed

Section 4 A3 Number Equality Test
    [Documentation]    Verifies equality for matching numeric text values.
    [Tags]    section-4    regression
    Should Be Equal    64    64

Section 4 A3 Word Contains Test
    [Documentation]    Verifies that a sample phrase contains the expected word.
    [Tags]    section-4    regression
    Should Contain    clean result    clean