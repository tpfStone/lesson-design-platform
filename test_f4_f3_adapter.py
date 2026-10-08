from adapters.f4_f3_adapter import (
    convert_f4_sections_to_f3_materials
)


sections = [

    {
        "id":"001",
        "title":"教学目标",
        "section_type":"objectives",
        "current_content":"认识数字编码"
    },


    {
        "id":"002",
        "title":"新知探究",
        "section_type":"exploration",
        "current_content":"教师引导学生探索数字编码规律"
    },


    {
        "id":"003",
        "title":"课堂练习",
        "section_type":"practice",
        "current_content":"完成数字编码练习"
    }

]


materials = convert_f4_sections_to_f3_materials(
    sections
)


print(materials)